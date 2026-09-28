import re, secrets, sqlite3
from functools import wraps
from flask import Blueprint, request, jsonify, session, render_template, g
from werkzeug.security import generate_password_hash, check_password_hash
from . import get_db

bp = Blueprint("main", __name__)

def user():
    uid = session.get("user_id")
    return get_db().execute("""SELECT u.*,r.name role FROM users u JOIN roles r ON r.id=u.role_id
                               WHERE u.id=? AND u.active=1""",(uid,)).fetchone() if uid else None

def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if not user(): return jsonify(error="Authentication required"),401
        return f(*a, **kw)
    return w

def roles(*allowed):
    def deco(f):
        @wraps(f)
        def w(*a, **kw):
            u=user()
            if not u: return jsonify(error="Authentication required"),401
            if u["role"] not in allowed: return jsonify(error="Forbidden"),403
            return f(*a, **kw)
        return w
    return deco

def audit(action, entity="", entity_id=None, desc=""):
    u=user()
    get_db().execute("INSERT INTO audit_logs(user_id,action,entity,entity_id,description) VALUES(?,?,?,?,?)",
                     (u["id"] if u else None,action,entity,entity_id,desc))

@bp.route("/")
def index(): return render_template("index.html")
@bp.route("/login")
def login_page(): return render_template("login.html")
@bp.route("/register")
def register_page(): return render_template("register.html")
@bp.route("/dashboard")
@login_required
def dashboard(): return render_template("dashboard.html")
@bp.route("/orders")
@login_required
def orders_page(): return render_template("orders.html")
@bp.route("/staff")
@roles("STAFF","ADMIN")
def staff_page(): return render_template("staff.html")
@bp.route("/admin")
@roles("ADMIN")
def admin_page(): return render_template("admin.html")

@bp.get("/health")
def health():
    get_db().execute("SELECT 1")
    return jsonify(status="healthy",database="connected")

@bp.post("/api/auth/register")
def register():
    d=request.get_json() or {}
    required=["full_name","student_id","email","phone","password","confirm_password"]
    if any(not str(d.get(x,"")).strip() for x in required): return jsonify(error="All fields are required"),400
    if d["password"] != d["confirm_password"]: return jsonify(error="Passwords do not match"),400
    if not re.fullmatch(r"(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}",d["password"]):
        return jsonify(error="Password must be 8+ chars with upper, lower, number and special character"),400
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",d["email"]): return jsonify(error="Invalid email"),400
    db=get_db()
    role=db.execute("SELECT id FROM roles WHERE name='STUDENT'").fetchone()[0]
    try:
        cur=db.execute("""INSERT INTO users(full_name,student_id,email,phone,password_hash,role_id,active)
                          VALUES(?,?,?,?,?,?,1)""",(d["full_name"],d["student_id"],d["email"],d["phone"],
                          generate_password_hash(d["password"]),role))
        audit("REGISTRATION","users",cur.lastrowid,"Student registered")
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback(); return jsonify(error="Email or Student ID already exists"),409
    return jsonify(message="Registration successful"),201

@bp.post("/api/auth/login")
def login():
    d=request.get_json() or {}
    u=get_db().execute("""SELECT u.*,r.name role FROM users u JOIN roles r ON r.id=u.role_id
                          WHERE lower(u.email)=lower(?) AND u.active=1""",(d.get("email",""),)).fetchone()
    if not u or not check_password_hash(u["password_hash"],d.get("password","")):
        return jsonify(error="Invalid credentials"),401
    session.clear(); session["user_id"]=u["id"]
    audit("LOGIN","users",u["id"],"Successful login"); get_db().commit()
    return jsonify(id=u["id"],name=u["full_name"],role=u["role"])

@bp.post("/api/auth/logout")
@login_required
def logout():
    audit("LOGOUT","users",user()["id"],"Logout"); get_db().commit(); session.clear()
    return jsonify(message="Logged out")

@bp.get("/api/me")
@login_required
def me():
    u=user(); return jsonify(id=u["id"],name=u["full_name"],email=u["email"],role=u["role"])

@bp.get("/api/menu")
def menu():
    rows=get_db().execute("""SELECT m.*,c.name category FROM menu_items m
                             JOIN menu_categories c ON c.id=m.category_id
                             WHERE m.availability=1 ORDER BY c.name,m.name""").fetchall()
    return jsonify(items=[dict(r) for r in rows])

@bp.post("/api/orders")
@login_required
@roles("STUDENT")
def create_order():
    d=request.get_json() or {}; items=d.get("items",[])
    if not items: return jsonify(error="Cart is empty"),400
    db=get_db(); u=user()
    try:
        db.execute("BEGIN")
        total=0; checked=[]
        for x in items:
            row=db.execute("SELECT * FROM menu_items WHERE id=? AND availability=1",(x.get("id"),)).fetchone()
            q=int(x.get("quantity",0))
            if not row or q<1 or q>row["stock_quantity"]: raise ValueError("Item unavailable or insufficient stock")
            total += row["price"]*q; checked.append((row,q))
        public=f"SC-{__import__('datetime').datetime.now().year}-{secrets.token_hex(3).upper()}"
        token=db.execute("SELECT COALESCE(MAX(token_number),100)+1 FROM orders WHERE canteen_id=1").fetchone()[0]
        cur=db.execute("""INSERT INTO orders(public_order_id,user_id,canteen_id,token_number,total,status,pickup_slot)
                          VALUES(?,?,?,?,?,?,?)""",(public,u["id"],1,token,total,"ORDER_PLACED",d.get("pickup_slot","ASAP")))
        oid=cur.lastrowid
        for row,q in checked:
            db.execute("INSERT INTO order_items(order_id,menu_item_id,quantity,unit_price) VALUES(?,?,?,?)",(oid,row["id"],q,row["price"]))
            db.execute("UPDATE menu_items SET stock_quantity=stock_quantity-? WHERE id=?",(q,row["id"]))
        db.execute("INSERT INTO queue(order_id,position,status) VALUES(?,?,?)",(oid,token-100,"WAITING"))
        db.execute("INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)",(u["id"],"Order placed",f"Your token is #{token}"))
        audit("ORDER_CREATED","orders",oid,public); db.commit()
    except Exception as e:
        db.rollback(); return jsonify(error=str(e)),400
    return jsonify(order_id=public,token=token,status="ORDER_PLACED"),201

@bp.get("/api/orders")
@login_required
def orders():
    u=user()
    rows=get_db().execute("""SELECT o.*, GROUP_CONCAT(m.name||' x'||oi.quantity, ', ') items
                             FROM orders o JOIN order_items oi ON oi.order_id=o.id
                             JOIN menu_items m ON m.id=oi.menu_item_id
                             WHERE o.user_id=? GROUP BY o.id ORDER BY o.id DESC""",(u["id"],)).fetchall()
    return jsonify(orders=[dict(r) for r in rows])

@bp.post("/api/orders/<int:oid>/cancel")
@login_required
@roles("STUDENT")
def cancel_order(oid):
    db=get_db(); u=user(); row=db.execute("SELECT * FROM orders WHERE id=? AND user_id=?",(oid,u["id"])).fetchone()
    if not row: return jsonify(error="Order not found"),404
    if row["status"] in ("COLLECTED","CANCELLED"): return jsonify(error="Order cannot be cancelled"),400
    if row["status"] == "READY": return jsonify(error="Order is already ready for pickup"),400

    items=db.execute("SELECT menu_item_id, quantity FROM order_items WHERE order_id=?",(oid,)).fetchall()
    for item in items:
        db.execute("UPDATE menu_items SET stock_quantity=stock_quantity+? WHERE id=?",(item["quantity"], item["menu_item_id"]))

    db.execute("UPDATE orders SET status='CANCELLED' WHERE id=?",(oid,))
    db.execute("UPDATE queue SET status='CANCELLED' WHERE order_id=?",(oid,))
    db.execute("INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)",(u["id"],"Order cancelled",f"Order {row['public_order_id']} was cancelled. Stock has been restored."))
    audit("ORDER_CANCELLED","orders",oid,f"Student cancelled {row['public_order_id']}"); db.commit()
    return jsonify(message="Order cancelled", order_id=row["public_order_id"])

@bp.get("/api/queue/my-position")
@login_required
@roles("STUDENT")
def my_queue():
    u=user(); row=get_db().execute("""SELECT o.token_number,o.status,
        (SELECT COUNT(*) FROM orders p WHERE p.canteen_id=o.canteen_id AND p.id<o.id
         AND p.status IN ('ORDER_PLACED','ACCEPTED','PREPARING')) position
        FROM orders o WHERE o.user_id=? AND o.status NOT IN ('COLLECTED','CANCELLED')
        ORDER BY o.id DESC LIMIT 1""",(u["id"],)).fetchone()
    return jsonify(dict(row) if row else {})

@bp.get("/api/notifications")
@login_required
def notifications():
    rows=get_db().execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 30",(user()["id"],)).fetchall()
    return jsonify(notifications=[dict(r) for r in rows])

@bp.put("/api/notifications/<int:nid>/read")
@login_required
def read_notification(nid):
    get_db().execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",(nid,user()["id"])); get_db().commit()
    return jsonify(message="Read")

@bp.get("/api/staff/orders")
@roles("STAFF","ADMIN")
def staff_orders():
    rows=get_db().execute("""SELECT o.*,u.full_name student,
        GROUP_CONCAT(m.name||' x'||oi.quantity, ', ') items
        FROM orders o JOIN users u ON u.id=o.user_id JOIN order_items oi ON oi.order_id=o.id
        JOIN menu_items m ON m.id=oi.menu_item_id GROUP BY o.id ORDER BY o.id DESC""").fetchall()
    return jsonify(orders=[dict(r) for r in rows])

@bp.put("/api/staff/orders/<int:oid>/status")
@roles("STAFF","ADMIN")
def status(oid):
    d=request.get_json() or {}; new=d.get("status")
    allowed={"ORDER_PLACED":"ACCEPTED","ACCEPTED":"PREPARING","PREPARING":"READY","READY":"COLLECTED"}
    row=get_db().execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
    if not row or allowed.get(row["status"])!=new: return jsonify(error="Invalid status transition"),400
    db=get_db(); db.execute("UPDATE orders SET status=? WHERE id=?",(new,oid))
    db.execute("UPDATE queue SET status=? WHERE order_id=?",(new,oid))
    db.execute("INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)",(row["user_id"],"Order update",f"Order {row['public_order_id']} is {new}"))
    audit("STATUS_CHANGED","orders",oid,f"{row['status']} -> {new}"); db.commit()
    return jsonify(message="Updated")

@bp.post("/api/staff/orders/<int:oid>/verify")
@roles("STAFF","ADMIN")
def verify(oid):
    row=get_db().execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
    if not row or row["status"]!="READY": return jsonify(error="Order is not ready"),400
    db=get_db(); db.execute("UPDATE orders SET status='COLLECTED' WHERE id=?",(oid,))
    db.execute("UPDATE queue SET status='COLLECTED' WHERE order_id=?",(oid,))
    audit("QR_VERIFIED","orders",oid,"QR/order verification completed"); db.commit()
    return jsonify(message="Collected")

@bp.get("/api/admin/analytics")
@roles("ADMIN")
def analytics():
    db=get_db()
    total=db.execute("SELECT COUNT(*) FROM users WHERE role_id=(SELECT id FROM roles WHERE name='STUDENT')").fetchone()[0]
    orders=db.execute("SELECT COUNT(*) FROM orders WHERE date(created_at)=date('now')").fetchone()[0]
    revenue=db.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE date(created_at)=date('now') AND status!='CANCELLED'").fetchone()[0]
    return jsonify(students=total,today_orders=orders,revenue=revenue,active_queue=db.execute("SELECT COUNT(*) FROM queue WHERE status NOT IN ('COLLECTED','CANCELLED')").fetchone()[0])

@bp.get("/api/admin/audit-logs")
@roles("ADMIN")
def logs():
    rows=get_db().execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100").fetchall()
    return jsonify(logs=[dict(r) for r in rows])
