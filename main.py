import asyncio
import logging
import os
import aiohttp
from aiohttp import web
from aiogram import types, Router
from config import BACKUP_CHAT_ID, WEBHOOK_SECRET
from datetime import datetime
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
)
from aiogram.utils.media_group import MediaGroupBuilder
from typing import Callable, Dict, Any, Awaitable

from config import ADMIN_IDS, BOT_TOKEN
from database import (
    add_product, add_size, delete_product, delete_size,
    get_all_products, get_product_photos, get_product_with_sizes_and_prices,
    get_sizes_of_product, save_order,
    get_top_products, get_top_sizes, get_total_orders, get_total_revenue,
    get_products_count, get_product_by_index, get_categories,
    add_category, delete_category, init_db,
    product_exists, size_exists,
    get_product_name_by_id, get_sizes_and_prices_by_product
)

# ---------------------- ГЛОБАЛЬНОЕ ХРАНИЛИЩЕ СЕССИЙ ИИ ----------------------
ai_sessions = {}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ---------------------- MIDDLEWARE ДЛЯ ПЕРЕХВАТА ОШИБОК ----------------------
class ExceptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            logging.error(f"❌ Unhandled exception: {e}", exc_info=True)
            try:
                if isinstance(event, Message):
                    await event.answer("⚠️ Произошла техническая ошибка. Попробуйте позже или нажмите /start.")
                elif hasattr(event, 'message'):
                    await event.message.answer("⚠️ Ошибка. Нажмите /start.")
            except:
                pass
            return

dp.message.middleware(ExceptionMiddleware())
dp.callback_query.middleware(ExceptionMiddleware())

# ---------------------- СОСТОЯНИЯ ----------------------
class OrderState(StatesGroup):
    selecting_category = State()
    selecting_subcategory = State()
    selecting_size = State()
    choosing_delivery = State()
    waiting_phone = State()
    waiting_fio = State()
    waiting_address = State()

class AdminState(StatesGroup):
    choosing_category = State()
    choosing_subcategory = State()
    waiting_product_name = State()
    waiting_product_photo = State()
    waiting_more_photos = State()
    waiting_size_product = State()
    waiting_size_value = State()
    waiting_size_price = State()
    waiting_delete_product = State()
    waiting_delete_size_product = State()
    waiting_delete_size_value = State()
    managing_categories = State()
    waiting_new_category_name = State()
    waiting_delete_category = State()

# ---------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------------------
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def show_admin_panel(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить товар")],
            [KeyboardButton(text="📏 Добавить размер")],
            [KeyboardButton(text="🗑️ Удалить товар")],
            [KeyboardButton(text="❌ Удалить размер")],
            [KeyboardButton(text="📂 Категории")],
            [KeyboardButton(text="📦 Все товары")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👤 Режим покупателя")],
        ],
        resize_keyboard=True,
    )
    await message.answer("<b>🔧 АДМИН ПАНЕЛЬ</b>\n\nВыберите действие:", reply_markup=keyboard)

admin_nav_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="◀️ Назад")], [KeyboardButton(text="❌ Выход")]],
    resize_keyboard=True
)

def get_products_keyboard(products):
    buttons = [[KeyboardButton(text=p)] for p in products]
    buttons.append([KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Выход")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_sizes_keyboard(sizes):
    buttons = [[KeyboardButton(text=s)] for s in sizes]
    buttons.append([KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Выход")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

async def send_product_card(chat_id, category_id, product_index):
    product_id, product_name, sizes, photos, total = await get_product_by_index(product_index, category_id)
    if not product_id:
        logging.error(f"Не удалось получить товар: index={product_index}, category_id={category_id}")
        return None
    text = f"<b>{product_name}</b>\n\n"
    if sizes:
        for size, price in sizes.items():
            text += f"• {size} — {price} BYN\n"
    else:
        text += "Нет доступных размеров\n"
    text += f"\nТовар {product_index + 1} из {total}"
    from database import get_category_by_id
    cat_info = await get_category_by_id(category_id)
    if cat_info and cat_info["parent_id"]:
        back_callback = f"back_to_subcats_{cat_info['parent_id']}_{category_id}"
        back_text = "🔙 К подкатегориям"
    else:
        back_callback = "back_to_categories"
        back_text = "🔙 К категориям"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data=f"cat_prev_{category_id}_{product_index}"),
                InlineKeyboardButton(text="✅ Оформить заказ", callback_data=f"order|{product_id}"),
                InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"cat_next_{category_id}_{product_index}")
            ],
            [
                InlineKeyboardButton(text=back_text, callback_data=back_callback)
            ]
        ]
    )
    if photos:
        media_group = MediaGroupBuilder()
        for photo_id in photos:
            media_group.add_photo(media=photo_id)
        await bot.send_media_group(chat_id, media=media_group.build())
    msg = await bot.send_message(chat_id, text, reply_markup=keyboard)
    return msg.message_id

async def ensure_categories():
    from database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM categories WHERE id IS NULL")

        all_cats = await conn.fetch("SELECT id, name, parent_id FROM categories")
    existing = {row["name"]: row for row in all_cats}

    boots_subcats = [
        "NIKE MERCURIAL",
        "NIKE PHANTOM",
        "NIKE TIEMPO",
        "ADIDAS F50",
        "PUMA FUTURE",
        "Детские размеры",
        "🔥 На скидке (последние размеры)"
    ]

    root_cats = ["Бутсы", "Футбольные костюмы", "Вратарские перчатки", "Футболки"]

    for cat in root_cats:
        if cat not in existing:
            await add_category(cat)
            logging.info(f"Добавлена категория '{cat}'")

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM categories WHERE name = 'Бутсы'")
        if not row:
            await add_category("Бутсы")
            row = await conn.fetchrow("SELECT id FROM categories WHERE name = 'Бутсы'")
        boots_id = row["id"]

        for cat_name in boots_subcats:
            cat_row = await conn.fetchrow("SELECT id FROM categories WHERE name = $1", cat_name)
            if cat_row:
                await conn.execute(
                    "UPDATE categories SET parent_id = $1 WHERE id = $2",
                    boots_id, cat_row["id"]
                )
            else:
                await conn.execute(
                    "INSERT INTO categories (name, parent_id) VALUES ($1, $2) ON CONFLICT (name) DO NOTHING",
                    cat_name, boots_id
                )
                logging.info(f"Добавлена подкатегория '{cat_name}'")

# ---------------------- ПОКУПАТЕЛЬ: СТАРТ И КАТЕГОРИИ ----------------------
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await ensure_categories()
    if is_admin(message.from_user.id):
        await show_admin_panel(message)
        return
    categories = await get_categories()
    if not categories:
        await message.answer("⚠️ Каталог пуст. Зайдите позже.", reply_markup=ReplyKeyboardRemove())
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"cat_{cat_id}")] 
        for cat_id, name in categories
    ] + [
        [InlineKeyboardButton(text="🤖 Помощь ИИ‑консультанта", callback_data="ai_help")]
    ])
    await message.answer("Выберите категорию:", reply_markup=keyboard)
    await state.set_state(OrderState.selecting_category)

@dp.callback_query(OrderState.selecting_category, F.data.regexp(r"^cat_\d+$"))
async def select_category(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) != 2 or parts[1] == "None":
        await callback.answer("Ошибка: категория не найдена", show_alert=True)
        return
    cat_id = int(parts[1])
    subcats = await get_categories(parent_id=cat_id)
    if subcats:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"subcat_{cat_id}_{sub_id}")]
            for sub_id, name in subcats
        ] + [
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_categories")]
        ])
        await callback.message.edit_text("Выберите подкатегорию:", reply_markup=keyboard)
        await state.set_state(OrderState.selecting_subcategory)
        await callback.answer()
        return
    total = await get_products_count(cat_id)
    if total == 0:
        await callback.answer("В этой категории пока нет товаров", show_alert=True)
        return
    await state.update_data(current_category=cat_id, current_index=0, total_products=total)
    msg_id = await send_product_card(callback.message.chat.id, cat_id, 0)
    if msg_id is None:
        await callback.answer("Ошибка загрузки товара. Попробуйте позже.", show_alert=True)
    else:
        await state.update_data(catalog_message_id=msg_id)
    await callback.answer()

@dp.callback_query(OrderState.selecting_subcategory, F.data.regexp(r"^subcat_\d+_\d+$"))
async def select_subcategory(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    cat_id = int(parts[1])
    sub_id = int(parts[2])
    total = await get_products_count(sub_id)
    if total == 0:
        await callback.answer("В этой подкатегории пока нет товаров", show_alert=True)
        return
    await state.update_data(current_category=sub_id, current_index=0, total_products=total, parent_category=cat_id)
    msg_id = await send_product_card(callback.message.chat.id, sub_id, 0)
    if msg_id is None:
        await callback.answer("Ошибка загрузки товара. Попробуйте позже.", show_alert=True)
    else:
        await state.update_data(catalog_message_id=msg_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("cat_prev_"))
async def prev_product_cat(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("Ошибка")
        return
    cat_id = int(parts[2])
    current = int(parts[3])
    if current <= 0:
        await callback.answer("Это первый товар")
        return
    new_index = current - 1
    # total не нужен для prev, но проверим, что индекс не отрицательный
    msg_id = await send_product_card(callback.message.chat.id, cat_id, new_index)
    if msg_id:
        data = await state.get_data()
        old_msg_id = data.get("catalog_message_id")
        if old_msg_id:
            try:
                await bot.delete_message(callback.message.chat.id, old_msg_id)
            except:
                pass
        await state.update_data(catalog_message_id=msg_id, current_index=new_index, current_category=cat_id)
    else:
        await callback.answer("Ошибка загрузки")
    await callback.answer()

@dp.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    categories = await get_categories()
    if not categories:
        await callback.message.answer("Каталог пуст.")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"cat_{cat_id}")] 
            for cat_id, name in categories
        ] + [
            [InlineKeyboardButton(text="🤖 Помощь ИИ‑консультанта", callback_data="ai_help")]
        ]
    )
    await callback.message.answer("Выберите категорию:", reply_markup=keyboard)
    await state.set_state(OrderState.selecting_category)
    await callback.answer()

@dp.callback_query(F.data.startswith("back_to_subcats_"))
async def back_to_subcategories(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    cat_id = int(parts[2])
    sub_id = int(parts[3])
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    subcats = await get_categories(parent_id=cat_id)
    if not subcats:
        categories = await get_categories()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"cat_{cat_id}")] for cat_id, name in categories
        ] + [
            [InlineKeyboardButton(text="🤖 Помощь ИИ‑консультанта", callback_data="ai_help")]
        ])
        await callback.message.answer("Выберите категорию:", reply_markup=keyboard)
        await state.set_state(OrderState.selecting_category)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"subcat_{cat_id}_{sub_id}")]
            for sub_id, name in subcats
        ] + [
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_categories")]
        ])
        await callback.message.answer("Выберите подкатегорию:", reply_markup=keyboard)
        await state.set_state(OrderState.selecting_subcategory)
    await callback.answer()

@dp.callback_query(F.data.startswith("cat_next_"))
async def next_product_cat(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("Ошибка")
        return
    cat_id = int(parts[2])
    current = int(parts[3])
    data = await state.get_data()
    total = data.get("total_products")
    if total is None:
        total = await get_products_count(cat_id)
        await state.update_data(total_products=total)
    if current + 1 >= total:
        await callback.answer("Это последний товар")
        return
    new_index = current + 1
    msg_id = await send_product_card(callback.message.chat.id, cat_id, new_index)
    if msg_id:
        old_msg_id = data.get("catalog_message_id")
        if old_msg_id:
            try:
                await bot.delete_message(callback.message.chat.id, old_msg_id)
            except:
                pass
        await state.update_data(catalog_message_id=msg_id, current_index=new_index, current_category=cat_id)
    else:
        await callback.answer("Ошибка загрузки")
    await callback.answer()

# ---------------------- ОФОРМЛЕНИЕ ЗАКАЗА ----------------------
@dp.callback_query(F.data.startswith("order|"))
async def order_start(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass
    product_id_str = callback.data.split("|", 1)[1]
    if not product_id_str.isdigit():
        await callback.answer("❌ Неверный идентификатор товара.", show_alert=True)
        return
    product_id = int(product_id_str)
    product_name = await get_product_name_by_id(product_id)
    if not product_name:
        await callback.answer("❌ Товар больше недоступен.", show_alert=True)
        return
    sizes = await get_sizes_and_prices_by_product(product_name)
    if not sizes:
        await callback.answer("Нет доступных размеров", show_alert=True)
        data = await state.get_data()
        cat_id = data.get("current_category")
        if cat_id is not None:
            idx = data.get("current_index", 0)
            msg_id = await send_product_card(callback.message.chat.id, cat_id, idx)
            if msg_id:
                await state.update_data(catalog_message_id=msg_id)
        return
    await state.update_data(product_id=product_id, product_name=product_name)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{size} ({price} BYN)", callback_data=f"size|{product_id}|{size}|{price}")]
        for size, price in sizes.items()
    ] + [[InlineKeyboardButton(text="🔙 Назад в каталог", callback_data="back_to_catalog")]])
    msg = await callback.message.answer(f"Выберите размер для <b>{product_name}</b>:", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.selecting_size)
    await callback.answer()

@dp.callback_query(OrderState.selecting_size, F.data.startswith("size|"))
async def select_size(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("|")
    if len(parts) != 4:
        await callback.answer("Ошибка", show_alert=True)
        return
    _, product_id_str, size, price = parts
    if not product_id_str.isdigit():
        await callback.answer("Ошибка", show_alert=True)
        return
    product_id = int(product_id_str)
    product_name = await get_product_name_by_id(product_id)
    if not product_name:
        await callback.answer("❌ Товар не найден", show_alert=True)
        return
    await state.update_data(product_id=product_id, product_name=product_name, size=size, price=int(price))
    data = await state.get_data()
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(callback.message.chat.id, order_msg_id)
        except:
            pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚚 Доставка", callback_data="delivery_delivery")],
        [InlineKeyboardButton(text="🏪 Самовывоз", callback_data="delivery_pickup")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_sizes")]
    ])
    msg = await callback.message.answer(
        f"Вы выбрали <b>{product_name}</b>, размер {size}, цена {price} BYN.\n\nВыберите способ получения:",
        reply_markup=keyboard
    )
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.choosing_delivery)
    await callback.answer()

@dp.callback_query(OrderState.choosing_delivery, F.data.startswith("delivery_"))
async def delivery_method(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[1]
    delivery = "🚚 Доставка" if method == "delivery" else "🏪 Самовывоз"
    await state.update_data(delivery=delivery)
    data = await state.get_data()
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(callback.message.chat.id, order_msg_id)
        except:
            pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_delivery")]])
    msg = await callback.message.answer("📞 Отправьте ваш номер телефона (или введите вручную):\nОн нужен для связи.", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.waiting_phone)
    await callback.answer()

@dp.message(OrderState.waiting_phone)
async def phone_input(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone:
        await message.answer("❌ Введите номер телефона.")
        return
    await state.update_data(phone=phone)
    data = await state.get_data()
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(message.chat.id, order_msg_id)
        except:
            pass
    if data.get("delivery") == "🚚 Доставка":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_phone")]])
        msg = await message.answer("📝 Введите ваше ФИО:", reply_markup=keyboard)
        await state.update_data(order_message_id=msg.message_id)
        await state.set_state(OrderState.waiting_fio)
    else:
        await state.update_data(fio="Не указано", address="Самовывоз")
        await send_order(message, state, await state.get_data())

@dp.message(OrderState.waiting_fio)
async def fio_input(message: Message, state: FSMContext):
    await state.update_data(fio=message.text.strip())
    data = await state.get_data()
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(message.chat.id, order_msg_id)
        except:
            pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_fio")]])
    msg = await message.answer("🏠 Введите адрес отделения Европочты (с указанием города):", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.waiting_address)

@dp.message(OrderState.waiting_address)
async def address_input(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    data = await state.get_data()
    await send_order(message, state, data)

# ---------------------- НАВИГАЦИЯ "НАЗАД" В ЗАКАЗЕ ----------------------
@dp.callback_query(F.data == "back_to_catalog")
async def back_to_catalog(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    categories = await get_categories()
    if categories:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"cat_{cat_id}")] for cat_id, name in categories
        ] + [
            [InlineKeyboardButton(text="🤖 Помощь ИИ‑консультанта", callback_data="ai_help")]
        ])
        await callback.message.answer("Выберите категорию:", reply_markup=keyboard)
        await state.set_state(OrderState.selecting_category)
    else:
        await callback.message.answer("Каталог пуст. Нажмите /start")
    await callback.answer()

@dp.callback_query(F.data == "back_to_sizes")
async def back_to_sizes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("product_id")
    product_name = await get_product_name_by_id(product_id)
    if not product_name:
        product_name = data.get("product_name")
    sizes = await get_sizes_and_prices_by_product(product_name)
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(callback.message.chat.id, order_msg_id)
        except:
            pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{size} ({price} BYN)", callback_data=f"size|{product_id}|{size}|{price}")]
        for size, price in sizes.items()
    ] + [[InlineKeyboardButton(text="🔙 Назад в каталог", callback_data="back_to_catalog")]])
    msg = await callback.message.answer(f"Выберите размер для <b>{product_name}</b>:", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.selecting_size)
    await callback.answer()

@dp.callback_query(F.data == "back_to_delivery")
async def back_to_delivery(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_name = data.get("product_name")
    size = data.get("size")
    price = data.get("price")
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(callback.message.chat.id, order_msg_id)
        except:
            pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚚 Доставка", callback_data="delivery_delivery")],
        [InlineKeyboardButton(text="🏪 Самовывоз", callback_data="delivery_pickup")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_sizes")]
    ])
    msg = await callback.message.answer(
        f"Вы выбрали <b>{product_name}</b>, размер {size}, цена {price} BYN.\n\nВыберите способ получения:",
        reply_markup=keyboard
    )
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.choosing_delivery)
    await callback.answer()

@dp.callback_query(F.data == "back_to_phone")
async def back_to_phone(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    delivery = data.get("delivery")
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(callback.message.chat.id, order_msg_id)
        except:
            pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_delivery")]])
    msg = await callback.message.answer("📞 Отправьте ваш номер телефона (или введите вручную):\nОн нужен для связи.", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.waiting_phone)
    await callback.answer()

@dp.callback_query(F.data == "back_to_fio")
async def back_to_fio(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(callback.message.chat.id, order_msg_id)
        except:
            pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_phone")]])
    msg = await callback.message.answer("📝 Введите ваше ФИО:", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.waiting_fio)
    await callback.answer()

# ---------------------- ИИ-КОНСУЛЬТАНТ ----------------------
@dp.callback_query(F.data == "ai_help")
async def ai_help_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    ai_sessions[user_id] = True
    await callback.answer("✅ ИИ‑консультант активирован")
    await callback.message.answer(
        "🤖 Здравствуйте! Я ИИ‑помощник магазина 365footballby. "
        "Задавайте любые вопросы о товарах, наличии, размерах.\n"
        "Чтобы выйти из режима консультанта, отправьте /exit"
    )

@dp.message(Command("exit"))
async def exit_ai_mode(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in ai_sessions:
        del ai_sessions[user_id]
    await message.answer("🚪 Вы вышли из режима ИИ‑консультанта.")

async def forward_to_n8n_and_reply(message: Message):
    n8n_webhook_url = "https://elkarpano13.app.n8n.cloud/webhook/869a2c3a-da4d-46c1-ad7c-e7ac150b534f"
    username = message.from_user.username if message.from_user.username else None
    payload = {
        "chat_id": message.chat.id,
        "user_id": message.from_user.id,
        "message_text": message.text,
        "first_name": message.from_user.first_name,
        "username": username,
    }
    print(f"📤 Отправляю в n8n: {payload}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(n8n_webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                print(f"✅ Статус ответа n8n: {resp.status}")
                text_response = await resp.text()
                print(f"📦 Тело ответа (первые 500 символов): {text_response[:500]}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await message.answer(f"Ошибка связи: {e}")

# ---------------------- ОТПРАВКА ЗАКАЗА ----------------------
async def send_order(message: Message, state: FSMContext, data: dict):
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(message.chat.id, order_msg_id)
        except:
            pass
    user = message.from_user
    username = f"@{user.username}" if user.username else "Нет username"
    order_data = {
        'product_name': data.get('product_name'),
        'size': data.get('size'),
        'price': int(data.get('price')),
        'delivery': data.get('delivery'),
        'fio': data.get('fio', 'Не указано'),
        'phone': data.get('phone'),
        'address': data.get('address', 'Самовывоз'),
        'username': username,
        'user_id': user.id
    }
    await save_order(order_data)
    await notify_admins_about_order(order_data)
    await message.answer("✅ Заказ отправлен! С вами свяжутся.", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    categories = await get_categories()
    if categories:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"cat_{cat_id}")] for cat_id, name in categories
        ] + [
            [InlineKeyboardButton(text="🤖 Помощь ИИ‑консультанта", callback_data="ai_help")]
        ])
        await message.answer("Выберите категорию для продолжения покупок:", reply_markup=keyboard)
        await state.set_state(OrderState.selecting_category)
    else:
        await message.answer("Каталог пуст. Нажмите /start")

async def notify_admins_about_order(order_data: dict):
    created_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    if 'created_at' in order_data and order_data['created_at']:
        try:
            dt = datetime.fromisoformat(order_data['created_at'].replace('Z', '+00:00'))
            created_at = dt.astimezone().strftime("%d.%m.%Y %H:%M:%S")
        except:
            pass

    text = (
        f"🛒 <b>НОВЫЙ ЗАКАЗ</b>\n"
        f"🕒 <i>{created_at}</i>\n\n"
        f"👟 Товар: {order_data.get('product_name')}\n"
        f"📏 Размер: {order_data.get('size')}\n"
        f"💰 Цена: {order_data.get('price')} BYN\n"
        f"🚚 Получение: {order_data.get('delivery')}\n\n"
        f"👤 Клиент: {order_data.get('fio', 'Не указано')}\n"
        f"🆔 ID: <code>{order_data.get('user_id')}</code>\n"
        f"📱 Username: {order_data.get('username', 'Нет username')}\n"
        f"🔗 Ссылка: <a href='tg://user?id={order_data.get('user_id')}'>Написать</a>\n"
        f"📞 Телефон: {order_data.get('phone')}\n"
    )
    if order_data.get('delivery') == "🚚 Доставка":
        text += f"\n📦 ФИО: {order_data.get('fio')}\n🏠 Адрес: {order_data.get('address')}"

    photos = await get_product_photos(order_data.get('product_name'))
    product_photo = photos[0] if photos else None

    for admin_id in ADMIN_IDS:
        try:
            if product_photo:
                await bot.send_photo(admin_id, photo=product_photo, caption=text)
            else:
                await bot.send_message(admin_id, text)
        except Exception as e:
            logging.error(f"Не удалось отправить заказ админу {admin_id}: {e}")

# ---------------------- HTTP ЭНДПОИНТ ДЛЯ ПРИЁМА ЗАКАЗОВ ОТ N8N ----------------------
async def handle_n8n_order(request: web.Request) -> web.Response:
    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {WEBHOOK_SECRET}":
        logging.warning("Неверный токен при вызове n8n эндпоинта")
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)

    required = ["product", "size", "price", "delivery", "phone", "user_id"]
    for field in required:
        if field not in data:
            return web.json_response({"status": "error", "message": f"Missing {field}"}, status=400)

    try:
        data["price"] = int(data["price"])
    except:
        return web.json_response({"status": "error", "message": "Price must be integer"}, status=400)

    data.setdefault("fio", "Не указано")
    data.setdefault("address", "Самовывоз" if data.get("delivery") == "🏪 Самовывоз" else "")
    data.setdefault("username", "n8n-заказ")
    # Преобразуем product в product_name
    order_to_save = {
        'product_name': data.get('product'),
        'size': data.get('size'),
        'price': data.get('price'),
        'delivery': data.get('delivery'),
        'fio': data.get('fio'),
        'phone': data.get('phone'),
        'address': data.get('address'),
        'user_id': data.get('user_id'),
        'username': data.get('username')
    }
    await save_order(order_to_save)
    await notify_admins_about_order(order_to_save)
    return web.json_response({"status": "ok", "message": "Order created"})

# ---------------------- АДМИНСКИЕ ФУНКЦИИ ----------------------
@dp.message(F.text == "➕ Добавить товар")
async def admin_add_product_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    categories = await get_categories()
    if not categories:
        await message.answer("❌ Нет ни одной категории. Сначала создайте категорию через базу данных.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"admin_cat_{cat_id}")] for cat_id, name in categories
    ])
    await message.answer("Выберите категорию для нового товара:", reply_markup=keyboard)
    await state.set_state(AdminState.choosing_category)

@dp.callback_query(StateFilter(AdminState.choosing_category), F.data.startswith("admin_cat_"))
async def admin_choose_category(callback: CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[2])
    subcats = await get_categories(parent_id=cat_id)
    if subcats:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"admin_subcat_{cat_id}_{sub_id}")]
            for sub_id, name in subcats
        ])
        await callback.message.edit_text("Выберите подкатегорию:", reply_markup=keyboard)
        await state.set_state(AdminState.choosing_subcategory)
    else:
        await state.update_data(category_id=cat_id)
        await state.set_state(AdminState.waiting_product_name)
        await callback.message.answer("Введите название товара:", reply_markup=admin_nav_keyboard)
    await callback.answer()

@dp.callback_query(StateFilter(AdminState.choosing_subcategory), F.data.startswith("admin_subcat_"))
async def admin_choose_subcategory(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    sub_id = int(parts[3])
    await state.update_data(category_id=sub_id)
    await state.set_state(AdminState.waiting_product_name)
    await callback.message.answer("Введите название товара:", reply_markup=admin_nav_keyboard)
    await callback.answer()

@dp.message(AdminState.waiting_product_name)
async def admin_product_name(message: Message, state: FSMContext):
    if message.text in ["❌ Выход", "◀️ Назад"]:
        await state.clear()
        await show_admin_panel(message)
        return
    name = message.text.strip()
    if not name:
        await message.answer("❌ Название не может быть пустым. Введите название товара:")
        return
    if await product_exists(name):
        await message.answer("❌ Товар с таким названием уже существует. Введите другое название:")
        return
    await state.update_data(product_name=name, photos=[])
    await state.set_state(AdminState.waiting_product_photo)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="➕ Добавить ещё")], [KeyboardButton(text="✅ Готово")], [KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Выход")]],
        resize_keyboard=True
    )
    await message.answer("Отправьте фото товара (можно несколько). После каждого фото нажимайте '➕ Добавить ещё' или '✅ Готово':", reply_markup=keyboard)

@dp.message(AdminState.waiting_product_photo, F.photo)
async def admin_product_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"✅ Фото {len(photos)} добавлено. Отправьте ещё или нажмите '✅ Готово'.")

@dp.message(AdminState.waiting_product_photo, F.text.in_(["➕ Добавить ещё", "✅ Готово", "◀️ Назад", "❌ Выход"]))
async def admin_product_photo_nav(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("processing"):
        await message.answer("⏳ Подождите, предыдущее действие ещё выполняется...")
        return
    await state.update_data(processing=True)
    try:
        if message.text == "❌ Выход":
            await state.clear()
            await show_admin_panel(message)
            return
        if message.text == "◀️ Назад":
            await state.set_state(AdminState.waiting_product_name)
            await message.answer("Введите название товара:", reply_markup=admin_nav_keyboard)
            return
        if message.text == "✅ Готово":
            data = await state.get_data()
            photos = data.get("photos", [])
            if not photos:
                await message.answer("❌ Вы не отправили ни одного фото. Отправьте хотя бы одно.")
                return
            success = await add_product(data["product_name"], photos, data["category_id"])
            if success:
                await message.answer("✅ Товар добавлен")
            else:
                await message.answer("❌ Такой товар уже существует")
            await state.clear()
            await show_admin_panel(message)
    finally:
        await state.update_data(processing=False)

@dp.message(AdminState.waiting_product_photo)
async def admin_product_photo_invalid(message: Message):
    await message.answer("❌ Отправьте фото или используйте кнопки.")

@dp.message(F.text == "📏 Добавить размер")
async def admin_add_size_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    products = await get_all_products()
    if not products:
        await message.answer("Сначала добавьте товар.")
        return
    await state.set_state(AdminState.waiting_size_product)
    keyboard = get_products_keyboard(products)
    await message.answer("Выберите товар:", reply_markup=keyboard)

@dp.message(AdminState.waiting_size_product)
async def admin_size_product(message: Message, state: FSMContext):
    if message.text in ["❌ Выход", "◀️ Назад"]:
        await state.clear()
        await show_admin_panel(message)
        return
    product_name = message.text.strip()
    if product_name not in await get_all_products():
        await message.answer("❌ Товар не найден. Выберите из списка.")
        return
    await state.update_data(product=product_name)
    await state.set_state(AdminState.waiting_size_value)
    await message.answer("Введите размер:", reply_markup=admin_nav_keyboard)

@dp.message(AdminState.waiting_size_value)
async def admin_size_value(message: Message, state: FSMContext):
    if message.text in ["❌ Выход", "◀️ Назад"]:
        await state.set_state(AdminState.waiting_size_product)
        products = await get_all_products()
        keyboard = get_products_keyboard(products)
        await message.answer("Выберите товар:", reply_markup=keyboard)
        return
    await state.update_data(size=message.text.strip())
    await state.set_state(AdminState.waiting_size_price)
    await message.answer("Введите цену (только число):", reply_markup=admin_nav_keyboard)

@dp.message(AdminState.waiting_size_price)
async def admin_size_price(message: Message, state: FSMContext):
    if message.text in ["❌ Выход", "◀️ Назад"]:
        await state.set_state(AdminState.waiting_size_value)
        await message.answer("Введите размер:", reply_markup=admin_nav_keyboard)
        return
    try:
        price = int(message.text)
        if price <= 0:
            await message.answer("❌ Цена должна быть положительным числом. Попробуйте снова.")
            return
    except ValueError:
        await message.answer("❌ Цена должна быть числом. Попробуйте снова.")
        return
    data = await state.get_data()
    product_name = data["product"]
    size_value = data["size"]
    if await size_exists(product_name, size_value):
        await message.answer(f"❌ Размер «{size_value}» уже существует у товара «{product_name}».\nУдалите старый или введите другой размер.")
        return
    await add_size(product_name, size_value, price)
    await message.answer("✅ Размер добавлен")
    await state.clear()
    await show_admin_panel(message)

@dp.message(F.text == "🗑️ Удалить товар")
async def admin_delete_product_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    products = await get_all_products()
    if not products:
        await message.answer("⚠️ Нет товаров для удаления.")
        return
    await state.set_state(AdminState.waiting_delete_product)
    keyboard = get_products_keyboard(products)
    await message.answer("Выберите товар для удаления:", reply_markup=keyboard)

@dp.message(AdminState.waiting_delete_product)
async def admin_delete_product_confirm(message: Message, state: FSMContext):
    if message.text in ["❌ Выход", "◀️ Назад"]:
        await state.clear()
        await show_admin_panel(message)
        return
    product_name = message.text.strip()
    if product_name not in await get_all_products():
        await message.answer("❌ Товар не найден.")
        return
    if await delete_product(product_name):
        await message.answer(f"✅ Товар «{product_name}» удалён.")
    else:
        await message.answer("❌ Не удалось удалить.")
    await state.clear()
    await show_admin_panel(message)

@dp.message(F.text == "❌ Удалить размер")
async def admin_delete_size_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    products = await get_all_products()
    if not products:
        await message.answer("⚠️ Нет товаров.")
        return
    await state.set_state(AdminState.waiting_delete_size_product)
    keyboard = get_products_keyboard(products)
    await message.answer("Выберите товар, у которого удалить размер:", reply_markup=keyboard)

@dp.message(AdminState.waiting_delete_size_product)
async def admin_delete_size_product(message: Message, state: FSMContext):
    if message.text in ["❌ Выход", "◀️ Назад"]:
        await state.clear()
        await show_admin_panel(message)
        return
    product_name = message.text.strip()
    if product_name not in await get_all_products():
        await message.answer("❌ Товар не найден.")
        return
    sizes = await get_sizes_of_product(product_name)
    if not sizes:
        await message.answer("❌ У товара нет размеров.")
        await state.clear()
        await show_admin_panel(message)
        return
    await state.update_data(delete_size_product=product_name)
    keyboard = get_sizes_keyboard(sizes)
    await state.set_state(AdminState.waiting_delete_size_value)
    await message.answer(f"Выберите размер для удаления:", reply_markup=keyboard)

@dp.message(AdminState.waiting_delete_size_value)
async def admin_delete_size_confirm(message: Message, state: FSMContext):
    if message.text in ["❌ Выход", "◀️ Назад"]:
        await state.set_state(AdminState.waiting_delete_size_product)
        products = await get_all_products()
        keyboard = get_products_keyboard(products)
        await message.answer("Выберите товар:", reply_markup=keyboard)
        return
    size = message.text.strip()
    data = await state.get_data()
    product_name = data.get("delete_size_product")
    sizes = await get_sizes_of_product(product_name)
    if size not in sizes:
        await message.answer("❌ Такого размера нет.")
        return
    if await delete_size(product_name, size):
        await message.answer(f"✅ Размер «{size}» удалён.")
    else:
        await message.answer("❌ Не удалось удалить. Возможно, такого размера уже нет.")
    await state.clear()
    await show_admin_panel(message)

# ---------------------- УПРАВЛЕНИЕ КАТЕГОРИЯМИ ----------------------
@dp.message(F.text == "📂 Категории")
async def admin_categories_menu(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    root_cats = await get_categories()
    cat_lines = []
    for cat_id, name in root_cats:
        cat_lines.append(f"📂 <b>{name}</b> (id:{cat_id})")
        subcats = await get_categories(parent_id=cat_id)
        for sub_id, sub_name in subcats:
            cat_lines.append(f"   └ {sub_name} (id:{sub_id})")
    cat_list = "\n".join(cat_lines)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить категорию")],
            [KeyboardButton(text="🗑️ Удалить категорию")],
            [KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True
    )
    await message.answer(f"<b>📂 КАТЕГОРИИ</b>\n\n{cat_list}", reply_markup=keyboard)
    await state.set_state(AdminState.managing_categories)

@dp.message(AdminState.managing_categories, F.text == "➕ Добавить категорию")
async def admin_add_category_start(message: Message, state: FSMContext):
    await message.answer("Введите название новой категории:", reply_markup=admin_nav_keyboard)
    await state.set_state(AdminState.waiting_new_category_name)

@dp.message(AdminState.waiting_new_category_name)
async def admin_add_category_confirm(message: Message, state: FSMContext):
    if message.text in ["❌ Выход", "◀️ Назад"]:
        await state.clear()
        await show_admin_panel(message)
        return
    name = message.text.strip()
    if not name:
        await message.answer("❌ Название не может быть пустым. Введите название категории:")
        return
    if await add_category(name):
        await message.answer(f"✅ Категория «{name}» добавлена")
    else:
        await message.answer("❌ Такая категория уже существует")
    await state.clear()
    await show_admin_panel(message)

@dp.message(AdminState.managing_categories, F.text == "🗑️ Удалить категорию")
async def admin_delete_category_start(message: Message, state: FSMContext):
    categories = await get_categories()
    if not categories:
        await message.answer("❌ Нет категорий для удаления.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"delcat_{cat_id}")] for cat_id, name in categories
    ])
    await message.answer("Выберите категорию для удаления:", reply_markup=keyboard)

@dp.callback_query(AdminState.managing_categories, F.data.startswith("delcat_"))
async def admin_delete_category_confirm(callback: CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[1])
    if await delete_category(cat_id):
        await callback.answer("✅ Категория удалена", show_alert=True)
    else:
        await callback.answer("❌ Не удалось удалить", show_alert=True)
    await state.clear()
    await show_admin_panel(callback.message)

@dp.message(AdminState.managing_categories, F.text == "◀️ Назад")
async def admin_categories_back(message: Message, state: FSMContext):
    await state.clear()
    await show_admin_panel(message)

@dp.message(F.text == "📦 Все товары")
async def admin_all_products(message: Message):
    if not is_admin(message.from_user.id): return
    products = await get_product_with_sizes_and_prices()
    if not products:
        await message.answer("Нет товаров.")
        return
    for name, sizes in products.items():
        text = f"<b>{name}</b>\n\n"
        for size, price in sizes.items():
            text += f"• {size} — {price} BYN\n"
        photos = await get_product_photos(name)
        if photos:
            await message.answer_photo(photos[0], caption=text)
        else:
            await message.answer(text)

@dp.message(F.text == "📊 Статистика")
async def admin_statistics(message: Message):
    if not is_admin(message.from_user.id): return
    total_orders = await get_total_orders()
    total_revenue = await get_total_revenue()
    top_products = await get_top_products(5)
    top_sizes = await get_top_sizes(5)
    stat = f"<b>📊 СТАТИСТИКА ПРОДАЖ</b>\n\n📦 Заказов: <b>{total_orders}</b>\n💰 Выручка: <b>{total_revenue} BYN</b>\n\n<b>🏆 Топ товаров:</b>\n"
    if top_products:
        for i, (name, cnt) in enumerate(top_products, 1):
            stat += f"{i}. {name} — {cnt} шт.\n"
    else:
        stat += "Нет данных.\n"
    stat += "\n<b>👕 Топ размеров:</b>\n"
    if top_sizes:
        for i, (size, cnt) in enumerate(top_sizes, 1):
            stat += f"{i}. {size} — {cnt} шт.\n"
    else:
        stat += "Нет данных.\n"
    await message.answer(stat)

@dp.message(F.text == "👤 Режим покупателя")
async def switch_to_customer(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    await message.answer("Переход в режим покупателя...", reply_markup=ReplyKeyboardRemove())
    categories = await get_categories()
    if categories:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"cat_{cat_id}")] for cat_id, name in categories
        ] + [
            [InlineKeyboardButton(text="🤖 Помощь ИИ‑консультанта", callback_data="ai_help")]
        ])
        await message.answer("Выберите категорию:", reply_markup=keyboard)
        await state.set_state(OrderState.selecting_category)
    else:
        await message.answer("⚠️ Каталог пуст. Добавьте товары в админ-панели.")
        await show_admin_panel(message)

@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено", reply_markup=ReplyKeyboardRemove())
    if is_admin(message.from_user.id):
        await show_admin_panel(message)
    else:
        categories = await get_categories()
        if categories:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=name, callback_data=f"cat_{cat_id}")] for cat_id, name in categories
            ] + [
                [InlineKeyboardButton(text="🤖 Помощь ИИ‑консультанта", callback_data="ai_help")]
            ])
            await message.answer("Выберите категорию:", reply_markup=keyboard)
            await state.set_state(OrderState.selecting_category)
        else:
            await message.answer("Каталог пуст. Нажмите /start")

# ---------------------- ОБРАБОТЧИК ВСЕХ СООБЩЕНИЙ (FALLBACK) ----------------------
@dp.message()
async def handle_all_messages(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if user_id in ai_sessions and text:
        await forward_to_n8n_and_reply(message)
        return
    current_state = await state.get_state()
    if current_state:
        await message.answer("❓ Не понимаю. Нажмите /cancel, чтобы отменить текущее действие, или /start заново.")
    else:
        await message.answer("👋 Нажмите /start для начала работы.")

# ---------------------- ПЕРЕХВАТ НЕИЗВЕСТНЫХ CALLBACK ----------------------
@dp.callback_query()
async def catch_unknown_callback(callback: CallbackQuery):
    logging.warning(f"Неизвестный callback: {callback.data}")
    await callback.answer(f"❓ Неизвестная команда", show_alert=True)

# ---------------------- ЗАПУСК ----------------------
async def main():
    await init_db()
    try:
        await bot.send_message(BACKUP_CHAT_ID, "🟢 Бот запущен на Railway")
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение в BACKUP_CHAT_ID: {e}")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "🟢 Админ-панель активна. Уведомления о заказах отправляются напрямую.")
        except:
            logging.error(f"Не удалось написать админу {admin_id}")

    app = web.Application()
    app.router.add_post("/api/order_from_n8n", handle_n8n_order)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    logging.info(f"HTTP сервер для n8n запущен на порту {port}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())