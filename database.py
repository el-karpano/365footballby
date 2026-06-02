import sqlite3
import os

DB_NAME = os.getenv("DB_PATH", "shop.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_NAME) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        photo TEXT,
        category_id INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sizes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT,
        size TEXT,
        price INTEGER,
        UNIQUE(product_name, size)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT,
        size TEXT,
        price INTEGER,
        delivery TEXT,
        fio TEXT,
        phone TEXT,
        address TEXT,
        user_id INTEGER,
        username TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Для старых баз – добавим колонку username, если её нет
    try:
        cur.execute("ALTER TABLE orders ADD COLUMN username TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

def get_categories():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM categories")
    rows = cur.fetchall()
    conn.close()
    return [(row['id'], row['name']) for row in rows]

def get_category_name(category_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
    row = cur.fetchone()
    conn.close()
    return row['name'] if row else None

def add_category(name):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def add_product(name, photo_file_ids, category_id):
    try:
        conn = get_connection()
        cur = conn.cursor()
        photos_str = "|||".join(photo_file_ids) if photo_file_ids else None
        cur.execute(
            "INSERT INTO products(name, photo, category_id) VALUES (?, ?, ?)",
            (name, photos_str, category_id)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def get_all_products(category_id=None):
    conn = get_connection()
    cur = conn.cursor()
    if category_id is not None:
        cur.execute("SELECT name FROM products WHERE category_id = ? ORDER BY id", (category_id,))
    else:
        cur.execute("SELECT name FROM products ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_products_count(category_id=None):
    conn = get_connection()
    cur = conn.cursor()
    if category_id is not None:
        cur.execute("SELECT COUNT(*) FROM products WHERE category_id = ?", (category_id,))
    else:
        cur.execute("SELECT COUNT(*) FROM products")
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_product_by_index(index, category_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM products WHERE category_id = ? ORDER BY id", (category_id,))
    products = cur.fetchall()
    total = len(products)
    if 0 <= index < total:
        product_name = products[index][0]
        sizes = get_product_with_sizes_and_prices().get(product_name, {})
        photos = get_product_photos(product_name)
        conn.close()
        return product_name, sizes, photos, total
    conn.close()
    return None, None, None, 0

def get_product_photos(product_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT photo FROM products WHERE name = ?", (product_name,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return row[0].split("|||")
    return []

def get_product_with_sizes_and_prices():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM products ORDER BY id")
    products = cur.fetchall()
    result = {}
    for product in products:
        product_name = product[0]
        cur.execute("SELECT size, price FROM sizes WHERE product_name = ?", (product_name,))
        rows = cur.fetchall()
        result[product_name] = {row[0]: row[1] for row in rows}
    conn.close()
    return result

def delete_product(product_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM products WHERE name = ?", (product_name,))
    if not cur.fetchone():
        conn.close()
        return False
    cur.execute("DELETE FROM sizes WHERE product_name = ?", (product_name,))
    cur.execute("DELETE FROM products WHERE name = ?", (product_name,))
    conn.commit()
    conn.close()
    return True

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
            fio, phone, address, user_id, username
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('product'),
        data.get('size'),
        data.get('price'),
        data.get('delivery'),
        data.get('fio'),
        data.get('phone'),
        data.get('address'),
        data.get('user_id'),
        data.get('username')
    ))
    conn.commit()
    conn.close()

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

# ---------- ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ БЕЗОПАСНОСТИ ----------
def product_exists(product_name: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM products WHERE name = ?", (product_name,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists

def size_exists(product_name: str, size: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sizes WHERE product_name = ? AND size = ?", (product_name, size))
    exists = cur.fetchone() is not None
    conn.close()
    return exists

print("DB PATH:", DB_NAME)
init_db()