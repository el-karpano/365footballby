import sqlite3
import time
import logging
from datetime import datetime, timedelta

DB_NAME = "shop.db"
logger = logging.getLogger(__name__)

def get_db_connection():
    """Подключение с повторными попытками при блокировке"""
    for attempt in range(3):
        try:
            conn = sqlite3.connect(DB_NAME, timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError as e:
            if attempt == 2:
                logger.error(f"Не удалось подключиться к БД после 3 попыток: {e}")
                raise
            logger.warning(f"Попытка {attempt + 1} подключения к БД не удалась, повторяем...")
            time.sleep(0.5)

def init_db():
    """Создание таблиц"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Таблица товаров
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                photo_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица размеров
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sizes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT,
                size TEXT,
                price INTEGER,
                is_available BOOLEAN DEFAULT 1,
                FOREIGN KEY (product_name) REFERENCES products (name),
                UNIQUE(product_name, size)
            )
        ''')
        
        # Таблица для хранения заказов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                username TEXT,
                product_name TEXT,
                size TEXT,
                price INTEGER,
                delivery TEXT,
                fio TEXT,
                address TEXT,
                phone TEXT,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        logger.info("База данных инициализирована успешно")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        raise
    finally:
        conn.close()

def add_product(name, photo_file_id=None):
    """Добавление товара с фото"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if photo_file_id:
            cursor.execute(
                "INSERT INTO products (name, photo_file_id) VALUES (?, ?)",
                (name, photo_file_id)
            )
        else:
            cursor.execute(
                "INSERT INTO products (name) VALUES (?)",
                (name,)
            )
        conn.commit()
        logger.info(f"Товар добавлен: {name}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Товар уже существует: {name}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при добавлении товара {name}: {e}")
        return False
    finally:
        conn.close()

def get_all_products():
    """Получить все товары"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM products ORDER BY name")
        products = [row[0] for row in cursor.fetchall()]
        conn.close()
        return products
    except Exception as e:
        logger.error(f"Ошибка при получении списка товаров: {e}")
        return []

def get_product_with_photo(product_name):
    """Получить фото товара"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT photo_file_id FROM products WHERE name = ?",
            (product_name,)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Ошибка при получении фото для {product_name}: {e}")
        return None

def add_size(product_name, size, price=0):
    """Добавление размера с ценой"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM products WHERE name = ?", (product_name,))
        if not cursor.fetchone():
            logger.warning(f"Товар не найден: {product_name}")
            return False
        
        cursor.execute(
            "INSERT INTO sizes (product_name, size, price) VALUES (?, ?, ?)",
            (product_name, size, price)
        )
        conn.commit()
        logger.info(f"Размер {size} добавлен для {product_name} по цене {price}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Размер {size} уже существует для {product_name}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при добавлении размера: {e}")
        return False
    finally:
        conn.close()

def delete_size(product_name, size):
    """Удаление конкретного размера у товара"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "DELETE FROM sizes WHERE product_name = ? AND size = ?",
            (product_name, size)
        )
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Размер {size} удалён у {product_name}")
        return deleted
    except Exception as e:
        logger.error(f"Ошибка при удалении размера: {e}")
        return False
    finally:
        conn.close()

def get_product_with_sizes_and_prices():
    """Получить товары с размерами и ценами"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM products ORDER BY name")
        products = cursor.fetchall()
        
        result = {}
        for product in products:
            product_name = product[0]
            cursor.execute(
                "SELECT size, price FROM sizes WHERE product_name = ? AND is_available = 1 ORDER BY size",
                (product_name,)
            )
            sizes = cursor.fetchall()
            result[product_name] = {size: price for size, price in sizes}
        
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Ошибка при получении товаров с размерами: {e}")
        return {}

def delete_product(product_name):
    """Удалить товар полностью"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM sizes WHERE product_name = ?", (product_name,))
        cursor.execute("DELETE FROM products WHERE name = ?", (product_name,))
        conn.commit()
        logger.info(f"Товар удалён: {product_name}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении товара {product_name}: {e}")
        return False
    finally:
        conn.close()

def save_order(order_data):
    """Сохранить заказ в БД"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO orders (
                user_id, user_name, username, product_name, 
                size, price, delivery, fio, address, phone, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            order_data.get('user_id'),
            order_data.get('user_name'),
            order_data.get('username'),
            order_data.get('product'),
            order_data.get('size'),
            order_data.get('price'),
            order_data.get('delivery'),
            order_data.get('fio'),
            order_data.get('address'),
            order_data.get('phone'),
            'new'
        ))
        conn.commit()
        order_id = cursor.lastrowid
        logger.info(f"Заказ #{order_id} сохранён от пользователя {order_data.get('user_id')}")
        return order_id
    except Exception as e:
        logger.error(f"Ошибка при сохранении заказа: {e}")
        return None
    finally:
        conn.close()

def get_orders_count():
    """Получить количество заказов"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Ошибка при подсчёте заказов: {e}")
        return 0

# =========================
# НОВЫЕ ФУНКЦИИ ДЛЯ СТАТИСТИКИ
# =========================

def get_top_products(limit=10, days=None):
    """
    Получить самые продаваемые товары (по количеству заказов)
    days: за последние N дней (None - за всё время)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT 
                product_name,
                COUNT(*) as orders_count,
                SUM(price) as total_revenue,
                AVG(price) as avg_price
            FROM orders
            WHERE status != 'cancelled'
        '''
        
        params = []
        if days:
            query += " AND created_at >= datetime('now', ?)"
            params.append(f'-{days} days')
        
        query += '''
            GROUP BY product_name
            ORDER BY orders_count DESC, total_revenue DESC
            LIMIT ?
        '''
        params.append(limit)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                'name': row[0],
                'orders_count': row[1],
                'total_revenue': row[2],
                'avg_price': int(row[3]) if row[3] else 0
            }
            for row in results
        ]
    except Exception as e:
        logger.error(f"Ошибка при получении топ-товаров: {e}")
        return []

def get_top_sizes(limit=10, days=None):
    """
    Получить самые ходовые размеры (по всем товарам)
    days: за последние N дней (None - за всё время)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT 
                size,
                COUNT(*) as orders_count,
                SUM(price) as total_revenue,
                GROUP_CONCAT(DISTINCT product_name) as products
            FROM orders
            WHERE status != 'cancelled'
        '''
        
        params = []
        if days:
            query += " AND created_at >= datetime('now', ?)"
            params.append(f'-{days} days')
        
        query += '''
            GROUP BY size
            ORDER BY orders_count DESC
            LIMIT ?
        '''
        params.append(limit)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                'size': row[0],
                'orders_count': row[1],
                'total_revenue': row[2],
                'products': row[3].split(',')[:3] if row[3] else []
            }
            for row in results
        ]
    except Exception as e:
        logger.error(f"Ошибка при получении топ-размеров: {e}")
        return []

def get_sales_by_period(days=30):
    """Получить статистику продаж за период"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_orders,
                SUM(price) as total_revenue,
                AVG(price) as avg_order_value,
                COUNT(DISTINCT user_id) as unique_customers
            FROM orders
            WHERE status != 'cancelled'
            AND created_at >= datetime('now', ?)
        ''', (f'-{days} days',))
        
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            return {
                'total_orders': row[0],
                'total_revenue': row[1] or 0,
                'avg_order_value': int(row[2]) if row[2] else 0,
                'unique_customers': row[3] or 0
            }
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении статистики за период: {e}")
        return None

def backup_db():
    """Создать резервную копию базы данных"""
    try:
        import shutil
        import os
        
        backup_dir = "backups"
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{backup_dir}/shop_{timestamp}.db"
        
        shutil.copy(DB_NAME, backup_path)
        
        # Удаляем старые бэкапы (старше 30 дней)
        for file in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, file)
            if os.path.isfile(file_path):
                file_time = os.path.getmtime(file_path)
                if time.time() - file_time > 30 * 24 * 3600:
                    os.remove(file_path)
        
        logger.info(f"Создан бэкап БД: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Ошибка при создании бэкапа БД: {e}")
        return None

init_db()