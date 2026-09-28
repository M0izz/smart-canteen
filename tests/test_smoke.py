import pytest
import backend.app as app_module
from backend.app import get_db


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DB", str(tmp_path / "database.db"))
    return app_module.create_app()


def test_health(app):
    c = app.test_client()
    response = c.get("/health")
    assert response.status_code == 200
    assert response.get_json()["database_backend"] == "sqlite"


def test_student_menu_and_orders_pages(app):
    client = app.test_client()
    login = client.post("/api/auth/login", json={
        "email": "vrushali@example.com",
        "password": "Student@123",
    })
    assert login.status_code == 200

    menu = client.get("/dashboard")
    orders = client.get("/orders")
    assert menu.status_code == 200
    assert b"Today's menu" in menu.data
    assert b'id="cart"' not in menu.data
    assert orders.status_code == 200
    assert b"Your orders" in orders.data


def test_student_can_sign_in_if_audit_log_write_fails(app):
    with app.app_context():
        db = get_db()
        db.execute("DROP TABLE audit_logs")
        db.commit()

    client = app.test_client()
    login = client.post("/api/auth/login", json={
        "email": "vrushali@example.com",
        "password": "Student@123",
    })
    assert login.status_code == 200, login.get_data(as_text=True)
    assert client.get("/api/me").status_code == 200


def test_order_tracking_and_alerts_update_for_student_and_staff(app):
    student = app.test_client()
    staff = app.test_client()
    assert student.post("/api/auth/login", json={
        "email": "vrushali@example.com",
        "password": "Student@123",
    }).status_code == 200

    with app.app_context():
        item_id = get_db().execute(
            "SELECT id FROM menu_items WHERE name='Veg Thali' ORDER BY id LIMIT 1"
        ).fetchone()[0]

    order = student.post("/api/orders", json={"items": [{"id": item_id, "quantity": 1}]})
    assert order.status_code == 201, order.get_data(as_text=True)
    with app.app_context():
        order_id = get_db().execute(
            "SELECT id FROM orders WHERE public_order_id=?", (order.get_json()["order_id"],)
        ).fetchone()[0]

    assert staff.post("/api/auth/login", json={
        "email": "staff@example.com",
        "password": "Staff@123",
    }).status_code == 200
    staff_alerts = staff.get("/api/notifications").get_json()["notifications"]
    assert any(alert["title"] == "New order" for alert in staff_alerts)

    for status in ("ACCEPTED", "PREPARING", "READY"):
        response = staff.put(f"/api/staff/orders/{order_id}/status", json={"status": status})
        assert response.status_code == 200, response.get_data(as_text=True)
        assert student.get("/api/queue/my-position").get_json()["status"] == status

    collected = staff.post(f"/api/staff/orders/{order_id}/verify")
    assert collected.status_code == 200
    assert student.get("/api/queue/my-position").get_json() == {}
    student_alerts = student.get("/api/notifications").get_json()["notifications"]
    staff_alerts = staff.get("/api/notifications").get_json()["notifications"]
    assert any("has been collected" in alert["message"] for alert in student_alerts)
    assert any(alert["title"] == "Order collected" for alert in staff_alerts)
    assert staff.get("/api/staff/orders").get_json()["orders"] == []


def test_admin_analytics_loads(app):
    client = app.test_client()
    login = client.post("/api/auth/login", json={
        "email": "admin@example.com",
        "password": "Admin@123",
    })
    assert login.status_code == 200
    assert client.get("/api/admin/analytics").status_code == 200


def test_student_can_cancel_order_and_restore_stock(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO menu_items(canteen_id, category_id, name, description, price, availability, stock_quantity, preparation_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 1, "Cancel Test Dish", "Second test item", 90, 1, 13, 8),
        )
        db.commit()
        item_id = db.execute("SELECT id FROM menu_items WHERE name='Cancel Test Dish' ORDER BY id DESC LIMIT 1").fetchone()[0]

        client = app.test_client()
        login = client.post("/api/auth/login", json={
            "email": "vrushali@example.com",
            "password": "Student@123",
        })
        assert login.status_code == 200, login.get_data(as_text=True)

        before = get_db().execute("SELECT stock_quantity FROM menu_items WHERE id=?", (item_id,)).fetchone()[0]

        order = client.post("/api/orders", json={
            "items": [{"id": item_id, "quantity": 2}],
            "pickup_slot": "ASAP",
        })
        assert order.status_code == 201, order.get_data(as_text=True)
        notifications = client.get("/api/notifications").get_json()["notifications"]
        assert any(note["title"] == "Order placed" for note in notifications)
        history = client.get("/api/orders")
        assert history.status_code == 200
        assert history.get_json()["orders"][0]["items"] == "Cancel Test Dish x2"

        order_id = order.get_json()["order_id"]
        db_order = get_db().execute("SELECT id, status FROM orders WHERE public_order_id=?", (order_id,)).fetchone()
        assert db_order is not None

        cancel = client.post(f"/api/orders/{db_order['id']}/cancel")
        assert cancel.status_code == 200, cancel.get_data(as_text=True)

        updated = get_db().execute("SELECT status FROM orders WHERE id=?", (db_order['id'],)).fetchone()[0]
        after = get_db().execute("SELECT stock_quantity FROM menu_items WHERE id=?", (item_id,)).fetchone()[0]

        assert updated == "CANCELLED"
        assert after == before
