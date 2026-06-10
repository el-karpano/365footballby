-- Экспорт базы данных из SQLite в PostgreSQL
-- Создан автоматически

BEGIN;

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER,
    name TEXT
);

INSERT INTO categories (id, name) VALUES (1, 'NIKE MERCURIAL');
INSERT INTO categories (id, name) VALUES (2, 'NIKE PHANTOM');
INSERT INTO categories (id, name) VALUES (3, 'NIKE TIEMPO');
INSERT INTO categories (id, name) VALUES (4, 'ADIDAS F50');
INSERT INTO categories (id, name) VALUES (5, 'PUMA FUTURE');
INSERT INTO categories (id, name) VALUES (6, '🔥 На скидке (последние размеры)');

CREATE TABLE IF NOT EXISTS products (
    id INTEGER,
    name TEXT,
    photo TEXT,
    category_id INTEGER
);

INSERT INTO products (id, name, photo, category_id) VALUES (2, 'Puma Ca Pro Classic', 'AgACAgIAAxkBAAITCGoioFJ--6OL0y7b1wjjzc4F_RKhAAJ8FmsbRqgQScsTFDdGufEBAQADAgADeAADOwQ', 1);
INSERT INTO products (id, name, photo, category_id) VALUES (3, 'Air Jordan 1 Low ''Olive Grey''', 'AgACAgIAAxkBAAITE2oioGrNIZ5D8nVpiRD3UvBZShhwAAJ-FmsbRqgQSXsCsdBDykeOAQADAgADeQADOwQ', 2);
INSERT INTO products (id, name, photo, category_id) VALUES (4, 'Nike C1TY Premium Cordura "Wheat"', 'AgACAgIAAxkBAAITHmoioH2Aot5Gi0n3mpnq-_nAMbK2AAKAFmsbRqgQSejKeGKpzZ4nAQADAgADeAADOwQ', 3);
INSERT INTO products (id, name, photo, category_id) VALUES (5, 'Von Dutch x Puma RS-2K ''Dark Denim Pink''', 'AgACAgIAAxkBAAITKWoioJSPqoB9NuF8nuKT7kNJioLjAAKBFmsbRqgQSYcre2FruW5qAQADAgADeQADOwQ', 4);
INSERT INTO products (id, name, photo, category_id) VALUES (6, 'Nike C1TY ''Smoke Grey Vachetta Tan''', 'AgACAgIAAxkBAAITNGoioKdy0jrz_ER50zkBatZEx_ttAAKCFmsbRqgQSRFMRZKtGxu8AQADAgADeQADOwQ', 5);
INSERT INTO products (id, name, photo, category_id) VALUES (7, 'Nike ACG Air Phassad ''Triple Black''', 'AgACAgIAAxkBAAITP2oioLvliGEb0NQ_QJwEcwoMro3_AAKDFmsbRqgQSW2atH-MBkKDAQADAgADeQADOwQ', 1);
INSERT INTO products (id, name, photo, category_id) VALUES (8, 'adidas Originals Adimatic ''Green White''', 'AgACAgIAAxkBAAITSmoioNGUfXGcUbbIHVH6pok8GHAXAAKFFmsbRqgQSQQBsMXd_gMMAQADAgADeQADOwQ', 3);
INSERT INTO products (id, name, photo, category_id) VALUES (9, 'adidas Yeezy 700 V3 ''Fade Carbon''', 'AgACAgIAAxkBAAITVWoioOCIp6S7J_WVBPh42r1p8jrfAAKGFmsbRqgQSbKXK-DI06DjAQADAgADeQADOwQ', 4);
INSERT INTO products (id, name, photo, category_id) VALUES (10, 'adidas Originals Adistar Control 5', 'AgACAgIAAxkBAAITYGoioPBC6e4wjOyItCz9stiI2SC9AAKIFmsbRqgQSUIhp8H1ZB77AQADAgADeQADOwQ', 5);
INSERT INTO products (id, name, photo, category_id) VALUES (11, 'Reebok Hammer Pro LTD', 'AgACAgIAAxkBAAITa2oioQJGCDv_wPqlIh1DGcyoAnn-AAKJFmsbRqgQSbbwQyAT7YTCAQADAgADeQADOwQ', 1);

CREATE TABLE IF NOT EXISTS sizes (
    id INTEGER,
    product_name TEXT,
    size TEXT,
    price INTEGER
);

INSERT INTO sizes (id, product_name, size, price) VALUES (2, 'Puma Ca Pro Classic', '40', 320);
INSERT INTO sizes (id, product_name, size, price) VALUES (3, 'Air Jordan 1 Low ''Olive Grey''', '40', 450);
INSERT INTO sizes (id, product_name, size, price) VALUES (4, 'Nike C1TY Premium Cordura "Wheat"', '40', 200);
INSERT INTO sizes (id, product_name, size, price) VALUES (5, 'Von Dutch x Puma RS-2K ''Dark Denim Pink''', '40', 440);
INSERT INTO sizes (id, product_name, size, price) VALUES (6, 'Nike C1TY ''Smoke Grey Vachetta Tan''', '40', 550);
INSERT INTO sizes (id, product_name, size, price) VALUES (7, 'Nike ACG Air Phassad ''Triple Black''', '41', 660);
INSERT INTO sizes (id, product_name, size, price) VALUES (8, 'adidas Originals Adimatic ''Green White''', '42', 180);
INSERT INTO sizes (id, product_name, size, price) VALUES (9, 'adidas Yeezy 700 V3 ''Fade Carbon''', '45', 500);
INSERT INTO sizes (id, product_name, size, price) VALUES (10, 'adidas Originals Adistar Control 5', '44', 400);
INSERT INTO sizes (id, product_name, size, price) VALUES (11, 'Reebok Hammer Pro LTD', '45', 330);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER,
    product_name TEXT,
    size TEXT,
    price INTEGER,
    delivery TEXT,
    fio TEXT,
    phone TEXT,
    address TEXT,
    user_id INTEGER,
    username TEXT,
    created_at TEXT
);

COMMIT;
