import sqlite3
import re

DB_PATH = "shop.db"  # Укажите имя вашего файла SQLite
OUTPUT_SQL = "database_export.sql"

def adapt_sqlite_value(value, col_type):
    """Преобразует значения SQLite в формат, понятный PostgreSQL."""
    if value is None:
        return "NULL"
    if isinstance(value, str):
        # Экранируем одинарные кавычки
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bytes):
        # Если есть BLOB, преобразуем в hex (или можно просто NULL, если не нужно)
        return f"'\\x{value.hex()}'"
    return f"'{str(value)}'"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем список всех таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]

    with open(OUTPUT_SQL, 'w', encoding='utf-8') as f:
        f.write("-- Экспорт базы данных из SQLite в PostgreSQL\n")
        f.write("-- Создан автоматически\n\n")
        f.write("BEGIN;\n\n")

        for table in tables:
            print(f"Обработка таблицы: {table}")
            # Получаем схему таблицы
            cursor.execute(f"PRAGMA table_info({table})")
            columns_info = cursor.fetchall()
            column_names = [col[1] for col in columns_info]
            column_types = [col[2] for col in columns_info]

            # Генерируем CREATE TABLE (максимально совместимо)
            create_sql = f"CREATE TABLE IF NOT EXISTS {table} (\n"
            for col_name, col_type in zip(column_names, column_types):
                pg_type = "TEXT"  # по умолчанию
                col_type_low = col_type.lower()
                if "int" in col_type_low:
                    pg_type = "INTEGER"
                elif "real" in col_type_low or "float" in col_type_low or "double" in col_type_low:
                    pg_type = "REAL"
                elif "blob" in col_type_low:
                    pg_type = "BYTEA"
                # остальное - TEXT
                create_sql += f"    {col_name} {pg_type},\n"
            create_sql = create_sql.rstrip(",\n") + "\n);\n\n"
            f.write(create_sql)

            # Выбираем данные
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            if not rows:
                continue

            # Генерируем INSERT для каждой строки
            for row in rows:
                values = [adapt_sqlite_value(val, col_type) for val, col_type in zip(row, column_types)]
                insert_sql = f"INSERT INTO {table} ({', '.join(column_names)}) VALUES ({', '.join(values)});\n"
                f.write(insert_sql)
            f.write("\n")

        f.write("COMMIT;\n")

    print(f"✅ Экспорт завершён. Файл: {OUTPUT_SQL}")
    conn.close()

if __name__ == "__main__":
    main()