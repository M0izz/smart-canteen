import pytest
import backend.app as app_module
from backend.app import get_db


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DB", str(tmp_path / "database.db"))
    return app_module.create_app()


def test_health(app):
    c = app.test_client()
    assert c.get("/health").status_code == 200


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
