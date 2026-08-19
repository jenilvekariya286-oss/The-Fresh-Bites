import os
import sqlite3
import json
import io
import qrcode
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates') if os.path.exists(os.path.join(BASE_DIR, 'templates')) else BASE_DIR

app = Flask(__name__, template_folder=TEMPLATES_DIR)
app.secret_key = "the_fresh_bites_secret_key_2026"

YOUR_UPI_ID = "jenillvekariya286@oksbi"
YOUR_NAME = "The Fresh Bites"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

DEFAULT_MENU = [
    {"id": 1, "name_en": "Cheese Burger", "name_gu": "ચીઝ બર્ગર", "price": 99, "stock": 15},
    {"id": 2, "name_en": "Club Sandwich", "name_gu": "ક્લબ સેન્ડવિચ", "price": 120, "stock": 15},
    {"id": 3, "name_en": "Cold Coco", "name_gu": "કોલ્ડ કોકો", "price": 60, "stock": 15}
]

DB_NAME = os.path.join(BASE_DIR, "my_new_restaurant.db")

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL;')
    
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
            address TEXT DEFAULT '',
            last_updated TEXT DEFAULT ''
        )
    ''')
    
    # ⚡ ઑટો-માઈગ્રેશન: જો જૂની DB માં last_updated કોલમ ન હોય તો આપમેળે ઉમેરાશે
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN last_updated TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # કોલમ પહેલેથી હાજર હોય ત્યારે સ્કીપ થશે

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            rating INTEGER,
            message TEXT,
            time TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY,
            name_en TEXT,
            name_gu TEXT,
            price INTEGER,
            stock INTEGER DEFAULT 15
        )
    ''')
    
    for item in DEFAULT_MENU:
        cursor.execute("SELECT id FROM inventory WHERE id = ?", (item['id'],))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO inventory (id, name_en, name_gu, price, stock) VALUES (?, ?, ?, ?, ?)",
                           (item['id'], item['name_en'], item['name_gu'], item['price'], item['stock']))

    conn.commit()
    conn.close()

init_db()

def get_db_menu_items():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name_en, name_gu, price, stock FROM inventory ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name_en": r[1], "name_gu": r[2], "price": r[3], "stock": r[4]} for r in rows]

def get_all_orders():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, customer_name, table_no, items, total, status, payment_mode, notes, order_type, phone, address, last_updated FROM orders ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    orders = []
    for row in rows:
        try:
            parsed_items = json.loads(row[4]) if row[4] else []
            orders.append({
                "id": row[0],
                "timestamp": str(row[1] or ""),
                "date": str(row[1] or ""),
                "customer_name": str(row[2] or "Unknown"),
                "table_no": str(row[3] or "N/A"),
                "items": parsed_items,
                "total": int(row[5]) if row[5] else 0,
                "status": str(row[6] or "Pending"),
                "payment_mode": str(row[7] or "Cash"),
                "notes": str(row[8] or ""),
                "order_type": str(row[9] or "Offline"),
                "phone": str(row[10] or ""),
                "address": str(row[11] or ""),
                "last_updated": str(row[12] or "")
            })
        except Exception:
            continue
    return orders

def get_all_reviews():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, rating, message, time FROM reviews ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"name": r[0], "rating": r[1], "message": r[2], "time": r[3]} for r in rows]

@app.route("/")
def home():
    available_tables = list(range(1, 11))
    current_menu = get_db_menu_items()
    return render_template("index.html", items=current_menu, restaurant_name=YOUR_NAME, available_tables=available_tables)

@app.route("/update-stock", methods=["POST"])
def update_stock():
    try:
        data = request.get_json(silent=True) or {}
        item_id = int(data.get("item_id"))
        new_stock = max(0, int(data.get("stock", 0)))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE inventory SET stock = ? WHERE id = ?", (new_stock, item_id))
        conn.commit()
        conn.close()
                
        return jsonify({"status": "success", "message": "Stock updated successfully!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/place-order", methods=["POST"])
def place_order():
    try:
        data = request.get_json(silent=True) or {}
        cart = data.get("cart", [])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        current_menu = get_db_menu_items()

        for cart_item in cart:
            c_id = cart_item.get("id")
            c_name = cart_item.get("name", "").lower()
            c_qty = int(cart_item.get("qty", 1))
            
            for item in current_menu:
                is_match = (c_id is not None and int(item["id"]) == int(c_id)) or (item["name_en"].lower() in c_name)
                if is_match:
                    if item["stock"] < c_qty:
                        conn.close()
                        return jsonify({
                            "status": "error", 
                            "message": f"Sorry! Only {item['stock']} left for {item['name_en']}."
                        }), 400

        for cart_item in cart:
            c_id = cart_item.get("id")
            c_name = cart_item.get("name", "").lower()
            c_qty = int(cart_item.get("qty", 1))
            
            for item in current_menu:
                is_match = (c_id is not None and int(item["id"]) == int(c_id)) or (item["name_en"].lower() in c_name)
                if is_match:
                    new_val = max(0, item["stock"] - c_qty)
                    cursor.execute("UPDATE inventory SET stock = ? WHERE id = ?", (new_val, item["id"]))

        customer_name = data.get("name", "Unknown")
        table_no = str(data.get("table", "N/A"))
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
        last_updated = str(datetime.now().timestamp())

        cursor.execute(
            "INSERT INTO orders (timestamp, customer_name, table_no, items, total, status, payment_mode, notes, order_type, phone, address, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (timestamp, customer_name, table_no, json.dumps(cart), total, 'Pending', payment_mode, notes, order_type, phone, address, last_updated)
        )
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success", 
            "message": "Order Confirmed", 
            "order_id": order_id
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/edit-order/<int:order_id>", methods=["POST"])
def edit_order(order_id):
    try:
        data = request.get_json(silent=True) or {}
        new_cart = data.get('cart', [])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT customer_name, table_no, items, total, notes FROM orders WHERE id = ?", (order_id,))
        old_order = cursor.fetchone()
        
        if old_order:
            old_cart = json.loads(old_order[2]) if old_order[2] else []
            
            old_qty_map = {}
            for item in old_cart:
                i_id = item.get('id')
                if i_id:
                    old_qty_map[int(i_id)] = old_qty_map.get(int(i_id), 0) + int(item.get('qty', 1))
            
            new_qty_map = {}
            for item in new_cart:
                i_id = item.get('id')
                if i_id:
                    new_qty_map[int(i_id)] = new_qty_map.get(int(i_id), 0) + int(item.get('qty', 1))
            
            all_item_ids = set(list(old_qty_map.keys()) + list(new_qty_map.keys()))
            for i_id in all_item_ids:
                old_q = old_qty_map.get(i_id, 0)
                new_q = new_qty_map.get(i_id, 0)
                diff = new_q - old_q
                
                if diff != 0:
                    cursor.execute("UPDATE inventory SET stock = MAX(0, stock - ?) WHERE id = ?", (diff, i_id))
            
            new_name = data.get('name', old_order[0])
            new_table = data.get('table', old_order[1])
            new_notes = data.get('notes', old_order[4])
            new_total = data.get('total', old_order[3])
            last_updated = str(datetime.now().timestamp())
            
            cursor.execute('''
                UPDATE orders 
                SET customer_name = ?, table_no = ?, items = ?, total = ?, notes = ?, last_updated = ?
                WHERE id = ?
            ''', (new_name, new_table, json.dumps(new_cart), new_total, new_notes, last_updated, order_id))
            
            conn.commit()
        
        conn.close()
        return jsonify({"status": "success", "message": "Order Updated & Stock Synced!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/cancel-order/<int:order_id>")
def cancel_order(order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT items, status FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
    
    if row and row[1] != 'Cancelled':
        try:
            cancelled_items = json.loads(row[0]) if row[0] else []
            for c_item in cancelled_items:
                c_id = c_item.get("id")
                c_qty = int(c_item.get("qty", 1))
                if c_id:
                    cursor.execute("UPDATE inventory SET stock = stock + ? WHERE id = ?", (c_qty, int(c_id)))
        except Exception:
            pass

    last_updated = str(datetime.now().timestamp())
    cursor.execute("UPDATE orders SET status = 'Cancelled', last_updated = ? WHERE id = ?", (last_updated, order_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Order Cancelled"})

@app.route("/complete-order/<int:order_id>")
def complete_order(order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    last_updated = str(datetime.now().timestamp())
    cursor.execute("UPDATE orders SET status = 'Completed', last_updated = ? WHERE id = ?", (last_updated, order_id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin-check-updates")
def admin_check_updates():
    orders = get_all_orders()
    inventory = get_db_menu_items()
    return jsonify({"status": "success", "orders": orders, "inventory": inventory})

@app.route("/get-cart-qr")
def get_cart_qr():
    try:
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin-login-check", methods=["POST"])
def admin_login_check():
    data = request.get_json(silent=True) or {}
    if data.get("user") == ADMIN_USERNAME and data.get("pass") == ADMIN_PASSWORD:
        session["admin"] = True
        return jsonify({"status": "success", "redirect": "/admin-dashboard"})
    return jsonify({"status": "error", "message": "Invalid Login"}), 401

@app.route("/admin-dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("home"))

    orders = get_all_orders()
    reviews = get_all_reviews()
    current_menu = get_db_menu_items()
    today_str = datetime.now().strftime("%d-%m-%Y")

    today_sales = sum(int(o.get("total", 0)) for o in orders if today_str in str(o.get("timestamp", "")) and str(o.get("status")).lower() != "cancelled")
    total_sales = sum(int(o.get("total", 0)) for o in orders if str(o.get("status")).lower() != "cancelled")
    cash_sales = sum(int(o.get("total", 0)) for o in orders if str(o.get("payment_mode")).lower() == "cash" and str(o.get("status")).lower() != "cancelled")
    online_sales = sum(int(o.get("total", 0)) for o in orders if str(o.get("payment_mode")).lower() == "online" and str(o.get("status")).lower() != "cancelled")

    return render_template(
        "admin.html",
        items=current_menu,
        orders=orders,
        today_sales=today_sales,
        total_sales=total_sales,
        cash_sales=cash_sales,
        online_sales=online_sales,
        reviews=reviews
    )

@app.route("/submit-review", methods=["POST"])
def submit_review():
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "Guest")
        rating = data.get("rating", 5)
        message = data.get("message", "")
        time_str = datetime.now().strftime("%d-%m-%Y %I:%M %p")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO reviews (name, rating, message, time) VALUES (?, ?, ?, ?)",
                       (name, rating, message, time_str))
        conn.commit()
        conn.close()

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/admin-logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
