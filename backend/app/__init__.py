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
    if db.execute("SELECT COUNT(*) FROM menu_categories").fetchone()[0] == 0:
        db.execute("INSERT INTO menu_categories(name) VALUES ('Meals'),('Snacks'),('Beverages')")
    if db.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0] == 0:
        items = [
            (1,1,"Veg Thali","Complete vegetarian meal",60,1,50,10),
            (1,2,"Masala Sandwich","Fresh grilled sandwich",45,1,50,8),
            (1,2,"Samosa","Crispy potato snack",20,1,100,5),
            (1,3,"Cold Coffee","Chilled coffee",40,1,60,5)
        ]
        db.executemany("INSERT INTO menu_items(canteen_id,category_id,name,description,price,availability,stock_quantity,preparation_time) VALUES(?,?,?,?,?,?,?,?)",items)
    db.commit()
    db.close()
