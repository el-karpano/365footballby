import asyncpg
import os
from typing import List, Tuple, Dict, Optional

DB_CONFIG = {
    "host": os.getenv("SUPABASE_HOST", "localhost"),
    "port": int(os.getenv("SUPABASE_PORT", 5432)),
    "database": os.getenv("SUPABASE_DB", "postgres"),
    "user": os.getenv("SUPABASE_USER", "postgres"),
    "password": os.getenv("SUPABASE_PASSWORD", ""),
}

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            **DB_CONFIG,
            min_size=1,
            max_size=10,
            command_timeout=60,
            statement_cache_size=0,
        )
    return _pool



async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                photo TEXT,
                category_id INTEGER
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sizes (
                id SERIAL PRIMARY KEY,
                product_name TEXT,
                size TEXT,
                price INTEGER,
                UNIQUE(product_name, size)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
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

async def get_categories() -> List[Tuple[int, str]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name FROM categories
            ORDER BY
                CASE name
                    WHEN '🔥 На скидке (последние размеры)' THEN 3
                    WHEN 'Детские размеры' THEN 2
                    ELSE 1
                END, id
        """)
        return [(row["id"], row["name"]) for row in rows]


async def get_category_name(category_id: int) -> Optional[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT name FROM categories WHERE id = $1", category_id)
        return row["name"] if row else None

async def add_category(name: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute("INSERT INTO categories (name) VALUES ($1)", name)
            return True
        except asyncpg.UniqueViolationError:
            return False

async def add_product(name: str, photo_file_ids: List[str], category_id: int) -> bool:
    pool = await get_pool()
    photos_str = "|||".join(photo_file_ids) if photo_file_ids else None
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO products(name, photo, category_id) VALUES ($1, $2, $3)",
                name, photos_str, category_id
            )
            return True
        except asyncpg.UniqueViolationError:
            return False

async def get_all_products(category_id: int = None) -> List[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if category_id is not None:
            rows = await conn.fetch("SELECT name FROM products WHERE category_id = $1 ORDER BY id", category_id)
        else:
            rows = await conn.fetch("SELECT name FROM products ORDER BY id")
        return [row["name"] for row in rows]

async def get_products_count(category_id: int = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if category_id is not None:
            count = await conn.fetchval("SELECT COUNT(*) FROM products WHERE category_id = $1", category_id)
        else:
            count = await conn.fetchval("SELECT COUNT(*) FROM products")
        return count

async def get_product_by_index(index: int, category_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT name FROM products WHERE category_id = $1 ORDER BY id", category_id)
        total = len(rows)
        if 0 <= index < total:
            product_name = rows[index]["name"]
            sizes = await get_product_with_sizes_and_prices()
            sizes = sizes.get(product_name, {})
            photos = await get_product_photos(product_name)
            return product_name, sizes, photos, total
        return None, None, None, 0

async def get_product_photos(product_name: str) -> List[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT photo FROM products WHERE name = $1", product_name)
        if row and row["photo"]:
            return row["photo"].split("|||")
        return []

async def get_product_with_sizes_and_prices() -> Dict[str, Dict[str, int]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        products = await conn.fetch("SELECT name FROM products ORDER BY id")
        result = {}
        for product in products:
            name = product["name"]
            rows = await conn.fetch("SELECT size, price FROM sizes WHERE product_name = $1", name)
            result[name] = {row["size"]: row["price"] for row in rows}
        return result

async def delete_product(product_name: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM products WHERE name = $1", product_name)
        if not exists:
            return False
        await conn.execute("DELETE FROM sizes WHERE product_name = $1", product_name)
        await conn.execute("DELETE FROM products WHERE name = $1", product_name)
        return True

async def add_size(product_name: str, size: str, price: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO sizes(product_name, size, price) VALUES ($1, $2, $3)",
                product_name, size, price
            )
            return True
        except asyncpg.UniqueViolationError:
            return False

async def delete_size(product_name: str, size: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM sizes WHERE product_name = $1 AND size = $2",
            product_name, size
        )
        return result == "DELETE 1"

async def get_sizes_of_product(product_name: str) -> List[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT size FROM sizes WHERE product_name = $1", product_name)
        return [row["size"] for row in rows]

async def save_order(data: dict):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO orders (
                product_name, size, price, delivery,
                fio, phone, address, user_id, username
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, data.get('product'), data.get('size'), data.get('price'), data.get('delivery'),
            data.get('fio'), data.get('phone'), data.get('address'),
            data.get('user_id'), data.get('username'))

async def get_total_orders() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM orders")
        return count

async def get_total_revenue() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT SUM(price) FROM orders")
        return total if total else 0

async def get_top_products(limit: int = 5) -> List[Tuple[str, int]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT product_name, COUNT(*) as count
            FROM orders
            GROUP BY product_name
            ORDER BY count DESC
            LIMIT $1
        """, limit)
        return [(row["product_name"], row["count"]) for row in rows]

async def get_top_sizes(limit: int = 5) -> List[Tuple[str, int]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT size, COUNT(*) as count
            FROM orders
            GROUP BY size
            ORDER BY count DESC
            LIMIT $1
        """, limit)
        return [(row["size"], row["count"]) for row in rows]

async def product_exists(product_name: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM products WHERE name = $1", product_name)
        return exists is not None

async def size_exists(product_name: str, size: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM sizes WHERE product_name = $1 AND size = $2", product_name, size)
        return exists is not None