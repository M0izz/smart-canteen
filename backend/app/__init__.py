import os, sqlite3
from flask import Flask, g
from werkzeug.security import generate_password_hash

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB = os.path.join(BASE, "database", "database.db")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

def create_app():
    app = Flask(__name__, template_folder=os.path.join(BASE,"frontend","templates"),
                static_folder=os.path.join(BASE,"frontend","static"))
    app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                     MAX_CONTENT_LENGTH=2*1024*1024)
    from .routes import bp
    app.register_blueprint(bp)

    @app.teardown_appcontext
    def close_db(exc=None):
        db = g.pop("db", None)
        if db: db.close()

    init_db(app)
    return app

def init_db(app):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute("PRAGMA foreign_keys=ON")
    schema = open(os.path.join(BASE,"database","schema.sql"), encoding="utf-8").read()
    db.executescript(schema)

    # Always ensure all three roles exist. This also repairs databases
    # created by an earlier version of the project.
    for role_name in ("STUDENT", "STAFF", "ADMIN"):
        db.execute("INSERT OR IGNORE INTO roles(name) VALUES (?)", (role_name,))
    roles = {r[0]: r[1] for r in db.execute("SELECT name,id FROM roles")}

    # Ensure demo accounts exist even when database.db already contains
    # another user. Passwords are hashed and are only for local demo use.
    demo_users = [
        ("Vrushali", "23CSE101", "vrushali@example.com", "9999999999", "Student@123", "STUDENT"),
        ("Canteen Staff", "STAFF001", "staff@example.com", "9999999998", "Staff@123", "STAFF"),
        ("System Admin", "ADMIN001", "admin@example.com", "9999999997", "Admin@123", "ADMIN"),
    ]
    for full_name, student_id, email, phone, password, role_name in demo_users:
        existing = db.execute("SELECT id FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
        if existing:
            db.execute("UPDATE users SET role_id=?, active=1 WHERE id=?", (roles[role_name], existing[0]))
        else:
            db.execute(
                "INSERT INTO users(full_name,student_id,email,phone,password_hash,role_id,active) VALUES(?,?,?,?,?,?,1)",
                (full_name, student_id, email, phone, generate_password_hash(password), roles[role_name])
            )

    # Seed basic canteen/menu data if missing.
    if db.execute("SELECT COUNT(*) FROM canteens").fetchone()[0] == 0:
        db.execute("INSERT INTO canteens(name,location,active) VALUES ('Main College Canteen','Campus',1)")
    for category_name in ("Meals", "Snacks", "Beverages"):
        db.execute("INSERT OR IGNORE INTO menu_categories(name) VALUES (?)", (category_name,))
    canteen_id = db.execute("SELECT id FROM canteens ORDER BY id LIMIT 1").fetchone()[0]
    categories = {row[0]: row[1] for row in db.execute("SELECT name,id FROM menu_categories")}
    items = [
        ("Veg Thali", "Complete vegetarian meal", 60, "Meals", 50, 10, "veg-thali.jpg"),
        ("Masala Sandwich", "Fresh grilled sandwich", 45, "Snacks", 50, 8, "masala-sandwich.jpg"),
        ("Samosa", "Crispy potato snack", 20, "Snacks", 100, 5, "samosa.jpg"),
        ("Cold Coffee", "Chilled coffee", 40, "Beverages", 60, 5, "cold-coffee.jpg"),
        ("Veg Biryani", "Fragrant rice with vegetables and warm spices", 95, "Meals", 30, 15, "veg-biryani.jpg"),
        ("Paneer Wrap", "Grilled paneer, crunchy greens, and mint chutney", 80, "Meals", 25, 10, "paneer-wrap.jpg"),
        ("Masala Dosa", "Crisp dosa with potato masala and sambar", 70, "Meals", 25, 12, "masala-dosa.jpg"),
        ("Idli Sambar", "Steamed idlis served with sambar and chutney", 55, "Meals", 35, 10, "idli-sambar.jpg"),
        ("Chole Bhature", "Spiced chickpeas with soft fried bhature", 85, "Meals", 25, 15, "chole-bhature.jpg"),
        ("Fruit Bowl", "Seasonal fruit, freshly cut", 50, "Snacks", 25, 5, "fruit-bowl.jpg"),
        ("Mango Lassi", "Chilled yogurt blended with mango", 45, "Beverages", 40, 5, "mango-lassi.jpg"),
        ("Lemon Iced Tea", "Black tea shaken with lemon and mint", 35, "Beverages", 40, 5, "lemon-iced-tea.jpg"),
    ]
    for name, description, price, category, stock, prep, image in items:
        existing = db.execute(
            "SELECT id FROM menu_items WHERE canteen_id=? AND lower(name)=lower(?) ORDER BY id LIMIT 1",
            (canteen_id, name),
        ).fetchone()
        image_path = f"/static/images/{image}"
        if existing:
            db.execute("UPDATE menu_items SET image=COALESCE(NULLIF(image,''),?) WHERE id=?", (image_path, existing[0]))
        else:
            db.execute(
                """INSERT INTO menu_items(canteen_id,category_id,name,description,price,availability,
                   stock_quantity,preparation_time,image) VALUES(?,?,?,?,?,1,?,?,?)""",
                (canteen_id, categories[category], name, description, price, stock, prep, image_path),
            )
    db.commit()
    db.close()
