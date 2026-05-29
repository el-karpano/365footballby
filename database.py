import sqlite3

DB_NAME = "shop.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            photo_file_id TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sizes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            size TEXT NOT NULL,
            price INTEGER NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            size TEXT NOT NULL,
            price INTEGER NOT NULL,
            delivery TEXT,
            customer_name TEXT,
            customer_phone TEXT,
            customer_address TEXT,
            customer_username TEXT,
            customer_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Добавляем недостающие колонки (если БД старая)
    cur.execute("PRAGMA table_info(orders)")
    columns = [col[1] for col in cur.fetchall()]
    if 'customer_name' not in columns:
        cur.execute("ALTER TABLE orders ADD COLUMN customer_name TEXT")
    if 'customer_phone' not in columns:
        cur.execute("ALTER TABLE orders ADD COLUMN customer_phone TEXT")
    if 'customer_address' not in columns:
        cur.execute("ALTER TABLE orders ADD COLUMN customer_address TEXT")
    if 'customer_username' not in columns:
        cur.execute("ALTER TABLE orders ADD COLUMN customer_username TEXT")
    if 'customer_id' not in columns:
        cur.execute("ALTER TABLE orders ADD COLUMN customer_id INTEGER")
    conn.commit()
    conn.close()

def add_product(name, photo_file_ids):
    """photo_file_ids - список строк file_id"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        photos_str = "|||".join(photo_file_ids) if photo_file_ids else None
        cur.execute("INSERT INTO products(name, photo_file_id) VALUES (?, ?)", (name, photos_str))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def get_all_products():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM products")
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]

def add_size(product_name, size, price):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO sizes(product_name, size, price) VALUES (?, ?, ?)", (product_name, size, price))
    conn.commit()
    conn.close()
    return True

def delete_size(product_name, size):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sizes WHERE product_name = ? AND size = ?", (product_name, size))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def delete_product(product_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM products WHERE name = ?", (product_name,))
    exists = cur.fetchone()
    if not exists:
        conn.close()
        return False
    cur.execute("DELETE FROM sizes WHERE product_name = ?", (product_name,))
    cur.execute("DELETE FROM products WHERE name = ?", (product_name,))
    conn.commit()
    conn.close()
    return True

def get_product_photos(product_name):
    """Возвращает список file_id фото товара"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT photo_file_id FROM products WHERE name = ?", (product_name,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return row[0].split("|||")
    return []

def get_product_with_sizes_and_prices():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM products")
    products = cur.fetchall()
    result = {}
    for product in products:
        product_name = product[0]
        cur.execute("SELECT size, price FROM sizes WHERE product_name = ?", (product_name,))
        rows = cur.fetchall()
        result[product_name] = {row[0]: row[1] for row in rows}
    conn.close()
    return result

def get_sizes_of_product(product_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT size FROM sizes WHERE product_name = ?", (product_name,))
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]

def save_order(data):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (
            product_name, size, price, delivery,
            customer_name, customer_phone, customer_address,
            customer_username, customer_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('product'),
        data.get('size'),
        data.get('price'),
        data.get('delivery'),
        data.get('fio'),
        data.get('phone'),
        data.get('address'),
        data.get('username'),
        data.get('user_id')
    ))
    conn.commit()
    conn.close()

def get_top_products(limit=5):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT product_name, COUNT(*) as count
        FROM orders
        GROUP BY product_name
        ORDER BY count DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [(row['product_name'], row['count']) for row in rows]

def get_top_sizes(limit=5):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT size, COUNT(*) as count
        FROM orders
        GROUP BY size
        ORDER BY count DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [(row['size'], row['count']) for row in rows]

def get_total_orders():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM orders")
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_total_revenue():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT SUM(price) FROM orders")
    total = cur.fetchone()[0]
    conn.close()
    return total if total else 0

def get_products_count():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM products")
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_product_by_index(index):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM products")
    products = cur.fetchall()
    if 0 <= index < len(products):
        product_name = products[index][0]
        sizes = get_product_with_sizes_and_prices().get(product_name, {})
        photos = get_product_photos(product_name)
        conn.close()
        return product_name, sizes, photos
    conn.close()
    return None, None, None

init_db()