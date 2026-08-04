from flask import Flask, render_template, request, send_file, jsonify, session, redirect, url_for, Response
import qrcode
import io
import sqlite3
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "jenil_secret_key_2026"

# ===========================
# Restaurant Details
# ===========================
YOUR_UPI_ID = "jenillvekariya286@oksbi"
YOUR_NAME = "The Fresh Bites"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

MENU_ITEMS = [
    {"id": 1, "name_en": "Cheese Burger", "name_gu": "ચીઝ બર્ગર", "price": 99},
    {"id": 2, "name_en": "Club Sandwich", "name_gu": "ક્લબ સેન્ડવિચ", "price": 120},
    {"id": 3, "name_en": "Cold Coco", "name_gu": "કોલ્ડ કોકો", "price": 60}
]

DB_NAME = "my_new_restaurant.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            customer_name TEXT,
            table_no TEXT,
            items TEXT,
            total INTEGER,
            status TEXT DEFAULT 'Pending',
            payment_mode TEXT DEFAULT 'Cash',
            notes TEXT DEFAULT '',
            order_type TEXT DEFAULT 'Offline',
            phone TEXT DEFAULT '',
            address TEXT DEFAULT ''
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            rating INTEGER,
            message TEXT,
            time TEXT
        )
    ''')
    
    for col, col_type in [("payment_mode", "TEXT DEFAULT 'Cash'"), 
                         ("notes", "TEXT DEFAULT ''"), 
                         ("order_type", "TEXT DEFAULT 'Offline'"), 
                         ("phone", "TEXT DEFAULT ''"), 
                         ("address", "TEXT DEFAULT ''")]:
        try:
            cursor.execute(f"ALTER TABLE orders ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

init_db()

def get_all_orders():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, customer_name, table_no, items, total, status, payment_mode, notes, order_type, phone, address FROM orders ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    orders = []
    for row in rows:
        try:
            parsed_items = json.loads(row[4]) if row[4] else []
            orders.append({
                "id": row[0],
                "timestamp": str(row[1] or ""),
                "customer_name": str(row[2] or "Unknown"),
                "table_no": str(row[3] or "N/A"),
                "items": parsed_items,
                "total": int(row[5]) if row[5] else 0,
                "status": str(row[6] or "Pending"),
                "payment_mode": str(row[7] or "Cash"),
                "notes": str(row[8] or ""),
                "order_type": str(row[9] or "Offline"),
                "phone": str(row[10] or ""),
                "address": str(row[11] or "")
            })
        except Exception:
            continue
    return orders

def get_all_reviews():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, rating, message, time FROM reviews ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"name": r[0], "rating": r[1], "message": r[2], "time": r[3]} for r in rows]

@app.route("/")
def home():
    return render_template("index.html", items=MENU_ITEMS, restaurant_name=YOUR_NAME)

@app.route("/admin-login-check", methods=["POST"])
def admin_login_check():
    data = request.get_json(silent=True) or {}
    if data.get("user") == ADMIN_USERNAME and data.get("pass") == ADMIN_PASSWORD:
        session["admin"] = True
        return jsonify({"status": "success", "redirect": "/admin-dashboard"})
    return jsonify({"status": "error", "message": "Invalid Login"}), 401

@app.route("/get-cart-qr")
def get_cart_qr():
    amount = request.args.get("amount", default="0")
    upi_url = f"upi://pay?pa={YOUR_UPI_ID}&pn={YOUR_NAME.replace(' ', '%20')}&am={amount}&cu=INR"

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=2)
    qr.add_data(upi_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img_io = io.BytesIO()
    img.save(img_io, "PNG")
    img_io.seek(0)
    return send_file(img_io, mimetype="image/png")

@app.route("/place-order", methods=["POST"])
def place_order():
    try:
        data = request.get_json(silent=True) or {}
        customer_name = data.get("name", "Unknown")
        table_no = data.get("table", "N/A")
        cart = data.get("cart", [])
        notes = data.get("notes", "")
        payment_mode = data.get("payment_mode", "Cash")
        order_type = data.get("order_type", "Offline")
        phone = data.get("phone", "")
        address = data.get("address", "")
        delivery_fee = int(data.get("delivery_fee", 0))
        
        try:
            total = int(float(data.get("total", 0)))
        except:
            total = 0

        if delivery_fee > 0:
            notes = f"[Delivery Fee: ₹{delivery_fee}] {notes}"

        timestamp = datetime.now().strftime("%d-%m-%Y %I:%M %p")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (timestamp, customer_name, table_no, items, total, status, payment_mode, notes, order_type, phone, address) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (timestamp, customer_name, table_no, json.dumps(cart), total, 'Pending', payment_mode, notes, order_type, phone, address)
        )
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success", 
            "message": "Order Confirmed", 
            "order_id": order_id,
            "estimated_time": "15-20 Mins"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/admin-dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("home"))

    orders = get_all_orders()
    reviews = get_all_reviews()

    today_str = datetime.now().strftime("%d-%m-%Y")

    today_sales = 0
    total_sales = 0
    cash_sales = 0
    online_sales = 0
    item_counts = {}

    for order in orders:
        status_val = str(order.get("status", ""))
        if status_val.lower() != "cancelled":
            amt = int(order.get("total", 0))
            total_sales += amt

            pay_mode = str(order.get("payment_mode", ""))
            if pay_mode.lower() == "online":
                online_sales += amt
            else:
                cash_sales += amt

            ts = str(order.get("timestamp", ""))
            if today_str in ts:
                today_sales += amt

            items = order.get("items", [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        item_name = str(item.get("name", "Item"))
                        qty = int(item.get("qty", 1))
                    else:
                        item_name = str(item)
                        qty = 1
                    
                    item_counts[item_name] = item_counts.get(item_name, 0) + qty

    item_counts_list = [{"name": k, "qty": v} for k, v in item_counts.items()]

    return render_template(
        "admin.html",
        orders=orders,
        today_sales=today_sales,
        total_sales=total_sales,
        cash_sales=cash_sales,
        online_sales=online_sales,
        item_counts=item_counts_list,
        reviews=reviews
    )

@app.route("/complete-order/<int:order_id>")
def complete_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = 'Completed' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/cancel-order/<int:order_id>")
def cancel_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = 'Cancelled' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin-check-updates")
def admin_check_updates():
    orders = get_all_orders()
    return jsonify({"status": "success", "orders": orders})

@app.route("/admin-logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)