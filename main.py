import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.utils.media_group import MediaGroupBuilder

from config import ADMIN_IDS, BOT_TOKEN
from database import (
    add_product,
    add_size,
    delete_product,
    delete_size,
    get_all_products,
    get_product_photos,
    get_product_with_sizes_and_prices,
    get_sizes_of_product,
    save_order,
    get_top_products,
    get_top_sizes,
    get_total_orders,
    get_total_revenue,
    get_products_count,
    get_product_by_index,
)

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())

# ---------------------- СОСТОЯНИЯ ----------------------
class OrderState(StatesGroup):
    selecting_size = State()
    choosing_delivery = State()
    waiting_phone = State()
    waiting_fio = State()
    waiting_address = State()

class AdminState(StatesGroup):
    waiting_product_name = State()
    waiting_product_photo = State()
    waiting_more_photos = State()
    waiting_size_product = State()
    waiting_size_value = State()
    waiting_size_price = State()
    waiting_delete_product = State()
    waiting_delete_size_product = State()
    waiting_delete_size_value = State()

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
            [KeyboardButton(text="📦 Все товары")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👤 Режим покупателя")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        "<b>🔧 АДМИН ПАНЕЛЬ</b>\n\nВыберите действие:",
        reply_markup=keyboard,
    )

async def send_product_card(chat_id, product_index):
    """Отправляет альбом фото и отдельное сообщение с кнопками."""
    product_name, sizes, photos = get_product_by_index(product_index)
    if not product_name:
        return None
    total = get_products_count()
    text = f"<b>{product_name}</b>\n\n"
    if sizes:
        for size, price in sizes.items():
            text += f"• {size} — {price} BYN\n"
    else:
        text += "Нет доступных размеров\n"
    text += f"\nТовар {product_index + 1} из {total}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"prev_{product_index}"),
            InlineKeyboardButton(text="✅ Оформить заказ", callback_data=f"order_{product_name}"),
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"next_{product_index}")
        ]
    ])

    # Отправляем альбом фото (без подписи)
    if photos:
        media_group = MediaGroupBuilder()
        for photo_id in photos:
            media_group.add_photo(media=photo_id)
        await bot.send_media_group(chat_id, media=media_group.build())
    # Отправляем отдельное сообщение с текстом и кнопками
    msg = await bot.send_message(chat_id, text, reply_markup=keyboard)
    return msg.message_id

# ---------------------- ПОКУПАТЕЛЬ: СТАРТ И КАТАЛОГ ----------------------
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    if is_admin(message.from_user.id):
        await show_admin_panel(message)
    else:
        await message.answer("Загрузка каталога...", reply_markup=ReplyKeyboardRemove())
        if get_products_count() == 0:
            await message.answer("⚠️ Каталог пуст. Зайдите позже.")
            return
        msg_id = await send_product_card(message.chat.id, 0)
        if msg_id:
            await state.update_data(catalog_message_id=msg_id, current_index=0)

@dp.callback_query(F.data.startswith("prev_"))
async def prev_product(callback: CallbackQuery, state: FSMContext):
    _, current = callback.data.split("_")
    current = int(current)
    if current > 0:
        new_index = current - 1
        # Удаляем старое сообщение с кнопками (альбом не удаляем, чтобы не было ошибок)
        data = await state.get_data()
        old_msg_id = data.get("catalog_message_id")
        if old_msg_id:
            try:
                await bot.delete_message(callback.message.chat.id, old_msg_id)
            except Exception as e:
                logging.warning(f"Не удалось удалить сообщение: {e}")
        # Отправляем новый товар
        msg_id = await send_product_card(callback.message.chat.id, new_index)
        if msg_id:
            await state.update_data(catalog_message_id=msg_id, current_index=new_index)
    await callback.answer()

@dp.callback_query(F.data.startswith("next_"))
async def next_product(callback: CallbackQuery, state: FSMContext):
    _, current = callback.data.split("_")
    current = int(current)
    total = get_products_count()
    if current + 1 < total:
        new_index = current + 1
        data = await state.get_data()
        old_msg_id = data.get("catalog_message_id")
        if old_msg_id:
            try:
                await bot.delete_message(callback.message.chat.id, old_msg_id)
            except Exception as e:
                logging.warning(f"Не удалось удалить сообщение: {e}")
        msg_id = await send_product_card(callback.message.chat.id, new_index)
        if msg_id:
            await state.update_data(catalog_message_id=msg_id, current_index=new_index)
    else:
        await callback.answer("Это последний товар")
    await callback.answer()

# ---------------------- ОФОРМЛЕНИЕ ЗАКАЗА (ВЫБОР РАЗМЕРА) ----------------------
@dp.callback_query(F.data.startswith("order_"))
async def order_start(callback: CallbackQuery, state: FSMContext):
    # Удаляем сообщение с кнопками (альбом остаётся)
    try:
        await callback.message.delete()
    except Exception as e:
        logging.warning(f"Не удалось удалить сообщение: {e}")
    product_name = callback.data.split("_", 1)[1]
    sizes = get_product_with_sizes_and_prices().get(product_name, {})
    if not sizes:
        await callback.answer("Нет доступных размеров", show_alert=True)
        # Возвращаем каталог (новое сообщение с кнопками для текущего товара)
        current_index = (await state.get_data()).get("current_index", 0)
        msg_id = await send_product_card(callback.message.chat.id, current_index)
        if msg_id:
            await state.update_data(catalog_message_id=msg_id, current_index=current_index)
        return
    await state.update_data(product=product_name)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{size} ({price} BYN)", callback_data=f"size_{product_name}_{size}_{price}")]
        for size, price in sizes.items()
    ] + [[InlineKeyboardButton(text="🔙 Назад в каталог", callback_data="back_to_catalog")]])
    msg = await callback.message.answer(f"Выберите размер для <b>{product_name}</b>:", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.selecting_size)
    await callback.answer()

# ---------------------- ВЫБОР РАЗМЕРА ----------------------
@dp.callback_query(OrderState.selecting_size, F.data.startswith("size_"))
async def select_size(callback: CallbackQuery, state: FSMContext):
    _, product_name, size, price = callback.data.split("_")
    await state.update_data(size=size, price=int(price))
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
    msg = await callback.message.answer(f"Вы выбрали <b>{product_name}</b>, размер {size}, цена {price} BYN.\n\nВыберите способ получения:", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.choosing_delivery)
    await callback.answer()

# ---------------------- СПОСОБ ДОСТАВКИ ----------------------
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_delivery")]
    ])
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
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_phone")]
        ])
        msg = await message.answer("📝 Введите ваше ФИО:", reply_markup=keyboard)
        await state.update_data(order_message_id=msg.message_id)
        await state.set_state(OrderState.waiting_fio)
    else:
        await state.update_data(fio="Не указано", address="Самовывоз")
        await send_order(message, state, data)

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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_fio")]
    ])
    msg = await message.answer("🏠 Введите адрес отделения Европочты в вашем городе (с указанием города):", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.waiting_address)

@dp.message(OrderState.waiting_address)
async def address_input(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    data = await state.get_data()
    await send_order(message, state, data)

# ---------------------- ОБРАБОТКА "НАЗАД" В ЗАКАЗЕ ----------------------
@dp.callback_query(F.data == "back_to_catalog")
async def back_to_catalog(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    # Возвращаем текущий товар с индекса 0
    msg_id = await send_product_card(callback.message.chat.id, 0)
    if msg_id:
        await state.update_data(catalog_message_id=msg_id, current_index=0)
    await callback.answer()

@dp.callback_query(F.data == "back_to_sizes")
async def back_to_sizes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_name = data.get("product")
    sizes = get_product_with_sizes_and_prices().get(product_name, {})
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(callback.message.chat.id, order_msg_id)
        except:
            pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{size} ({price} BYN)", callback_data=f"size_{product_name}_{size}_{price}")]
        for size, price in sizes.items()
    ] + [[InlineKeyboardButton(text="🔙 Назад в каталог", callback_data="back_to_catalog")]])
    msg = await callback.message.answer(f"Выберите размер для <b>{product_name}</b>:", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.selecting_size)
    await callback.answer()

@dp.callback_query(F.data == "back_to_delivery")
async def back_to_delivery(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_name = data.get("product")
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
    msg = await callback.message.answer(f"Вы выбрали <b>{product_name}</b>, размер {size}, цена {price} BYN.\n\nВыберите способ получения:", reply_markup=keyboard)
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
    if delivery == "🚚 Доставка":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_delivery")]
        ])
        msg = await callback.message.answer("📞 Отправьте ваш номер телефона (или введите вручную):\nОн нужен для связи.", reply_markup=keyboard)
        await state.update_data(order_message_id=msg.message_id)
        await state.set_state(OrderState.waiting_phone)
    else:
        await back_to_delivery(callback, state)
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_phone")]
    ])
    msg = await callback.message.answer("📝 Введите ваше ФИО:", reply_markup=keyboard)
    await state.update_data(order_message_id=msg.message_id)
    await state.set_state(OrderState.waiting_fio)
    await callback.answer()

# ---------------------- ОТПРАВКА ЗАКАЗА АДМИНАМ ----------------------
async def send_order(message: Message, state: FSMContext, data: dict):
    # Удаляем последнее сообщение с вопросом (ФИО или адрес)
    order_msg_id = data.get("order_message_id")
    if order_msg_id:
        try:
            await bot.delete_message(message.chat.id, order_msg_id)
        except:
            pass

    user = message.from_user
    username = f"@{user.username}" if user.username else "Нет username"
    profile_link = f"tg://user?id={user.id}"

    order_data = {
        'product': data.get('product'),
        'size': data.get('size'),
        'price': int(data.get('price')),
        'delivery': data.get('delivery'),
        'fio': data.get('fio'),
        'phone': data.get('phone'),
        'address': data.get('address'),
        'username': username,
        'user_id': user.id
    }
    save_order(order_data)

    text = (
        f"🛒 <b>НОВЫЙ ЗАКАЗ</b>\n\n"
        f"👟 Товар: {data.get('product')}\n"
        f"📏 Размер: {data.get('size')}\n"
        f"💰 Цена: {data.get('price')} BYN\n"
        f"🚚 Получение: {data.get('delivery')}\n\n"
        f"👤 Клиент: {user.full_name}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📱 Username: {username}\n"
        f"🔗 Ссылка: <a href='{profile_link}'>Написать</a>\n"
        f"📞 Телефон: {data.get('phone')}\n"
    )
    if data.get("delivery") == "🚚 Доставка":
        text += f"\n📦 ФИО: {data.get('fio')}\n🏠 Адрес: {data.get('address')}"

    photos = get_product_photos(data.get("product"))
    photo = photos[0] if photos else None
    for admin_id in ADMIN_IDS:
        try:
            if photo:
                await bot.send_photo(admin_id, photo=photo, caption=text)
            else:
                await bot.send_message(admin_id, text)
        except Exception as e:
            logging.error(e)

    await message.answer("✅ Заказ отправлен! С вами свяжутся.", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    # Возвращаем покупателя в каталог (первый товар)
    msg_id = await send_product_card(message.chat.id, 0)
    if msg_id:
        await state.update_data(catalog_message_id=msg_id, current_index=0)

# ---------------------- АДМИНСКИЕ ФУНКЦИИ (рабочие) ----------------------
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

@dp.message(F.text == "➕ Добавить товар")
async def admin_add_product(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminState.waiting_product_name)
    await message.answer("Введите название товара:", reply_markup=admin_nav_keyboard)

@dp.message(AdminState.waiting_product_name)
async def admin_product_name(message: Message, state: FSMContext):
    if message.text == "❌ Выход":
        await state.clear()
        await show_admin_panel(message)
        return
    if message.text == "◀️ Назад":
        await state.clear()
        await show_admin_panel(message)
        return
    await state.update_data(product_name=message.text.strip())
    await state.update_data(photos=[])
    await state.set_state(AdminState.waiting_product_photo)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить ещё")],
            [KeyboardButton(text="✅ Готово")],
            [KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Выход")]
        ],
        resize_keyboard=True
    )
    await message.answer("Отправьте фото товара (можно несколько). После каждого фото нажимайте '➕ Добавить ещё' или '✅ Готово':", reply_markup=keyboard)

@dp.message(AdminState.waiting_product_photo, F.text.in_(["➕ Добавить ещё", "✅ Готово", "◀️ Назад", "❌ Выход"]))
async def admin_product_photo_nav(message: Message, state: FSMContext):
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
        success = add_product(data["product_name"], photos)
        if success:
            await message.answer("✅ Товар добавлен")
        else:
            await message.answer("❌ Такой товар уже существует")
        await state.clear()
        await show_admin_panel(message)
        return
    # "➕ Добавить ещё" — просто ждём следующее фото

@dp.message(AdminState.waiting_product_photo, F.photo)
async def admin_product_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"✅ Фото {len(photos)} добавлено. Отправьте ещё или нажмите '✅ Готово'.")

@dp.message(AdminState.waiting_product_photo)
async def admin_product_photo_invalid(message: Message):
    await message.answer("❌ Отправьте фото или используйте кнопки.")

# ---------- Добавление размера ----------
@dp.message(F.text == "📏 Добавить размер")
async def admin_add_size(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    products = get_all_products()
    if not products:
        await message.answer("Сначала добавьте товар.")
        return
    await state.set_state(AdminState.waiting_size_product)
    keyboard = get_products_keyboard(products)
    await message.answer("Выберите товар:", reply_markup=keyboard)

@dp.message(AdminState.waiting_size_product)
async def admin_size_product(message: Message, state: FSMContext):
    if message.text == "❌ Выход":
        await state.clear()
        await show_admin_panel(message)
        return
    if message.text == "◀️ Назад":
        await state.clear()
        await show_admin_panel(message)
        return
    product_name = message.text.strip()
    if product_name not in get_all_products():
        await message.answer("❌ Товар не найден. Выберите из списка.")
        return
    await state.update_data(product=product_name)
    await state.set_state(AdminState.waiting_size_value)
    await message.answer("Введите размер:", reply_markup=admin_nav_keyboard)

@dp.message(AdminState.waiting_size_value, F.text.in_(["◀️ Назад", "❌ Выход"]))
async def admin_size_value_nav(message: Message, state: FSMContext):
    if message.text == "❌ Выход":
        await state.clear()
        await show_admin_panel(message)
        return
    if message.text == "◀️ Назад":
        await state.set_state(AdminState.waiting_size_product)
        products = get_all_products()
        keyboard = get_products_keyboard(products)
        await message.answer("Выберите товар:", reply_markup=keyboard)
        return

@dp.message(AdminState.waiting_size_value)
async def admin_size_value(message: Message, state: FSMContext):
    await state.update_data(size=message.text.strip())
    await state.set_state(AdminState.waiting_size_price)
    await message.answer("Введите цену (только число):", reply_markup=admin_nav_keyboard)

@dp.message(AdminState.waiting_size_price, F.text.in_(["◀️ Назад", "❌ Выход"]))
async def admin_size_price_nav(message: Message, state: FSMContext):
    if message.text == "❌ Выход":
        await state.clear()
        await show_admin_panel(message)
        return
    if message.text == "◀️ Назад":
        await state.set_state(AdminState.waiting_size_value)
        await message.answer("Введите размер:", reply_markup=admin_nav_keyboard)
        return

@dp.message(AdminState.waiting_size_price)
async def admin_size_price(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        price = int(message.text)
    except ValueError:
        await message.answer("❌ Цена должна быть числом. Попробуйте снова.")
        return
    add_size(data["product"], data["size"], price)
    await message.answer("✅ Размер добавлен")
    await state.clear()
    await show_admin_panel(message)

# ---------- Удаление товара ----------
@dp.message(F.text == "🗑️ Удалить товар")
async def admin_delete_product_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    products = get_all_products()
    if not products:
        await message.answer("⚠️ Нет товаров для удаления.")
        return
    await state.set_state(AdminState.waiting_delete_product)
    keyboard = get_products_keyboard(products)
    await message.answer("Выберите товар для удаления:", reply_markup=keyboard)

@dp.message(AdminState.waiting_delete_product, F.text.in_(["◀️ Назад", "❌ Выход"]))
async def admin_delete_product_nav(message: Message, state: FSMContext):
    if message.text == "❌ Выход":
        await state.clear()
        await show_admin_panel(message)
        return
    if message.text == "◀️ Назад":
        await state.clear()
        await show_admin_panel(message)
        return

@dp.message(AdminState.waiting_delete_product)
async def admin_delete_product_confirm(message: Message, state: FSMContext):
    product_name = message.text.strip()
    if product_name not in get_all_products():
        await message.answer("❌ Товар не найден.")
        return
    if delete_product(product_name):
        await message.answer(f"✅ Товар «{product_name}» удалён.")
    else:
        await message.answer(f"❌ Не удалось удалить.")
    await state.clear()
    await show_admin_panel(message)

# ---------- Удаление размера ----------
@dp.message(F.text == "❌ Удалить размер")
async def admin_delete_size_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    products = get_all_products()
    if not products:
        await message.answer("⚠️ Нет товаров.")
        return
    await state.set_state(AdminState.waiting_delete_size_product)
    keyboard = get_products_keyboard(products)
    await message.answer("Выберите товар, у которого удалить размер:", reply_markup=keyboard)

@dp.message(AdminState.waiting_delete_size_product, F.text.in_(["◀️ Назад", "❌ Выход"]))
async def admin_delete_size_product_nav(message: Message, state: FSMContext):
    if message.text == "❌ Выход":
        await state.clear()
        await show_admin_panel(message)
        return
    if message.text == "◀️ Назад":
        await state.clear()
        await show_admin_panel(message)
        return

@dp.message(AdminState.waiting_delete_size_product)
async def admin_delete_size_product(message: Message, state: FSMContext):
    product_name = message.text.strip()
    if product_name not in get_all_products():
        await message.answer("❌ Товар не найден.")
        return
    sizes = get_sizes_of_product(product_name)
    if not sizes:
        await message.answer("❌ У товара нет размеров.")
        await state.clear()
        await show_admin_panel(message)
        return
    await state.update_data(delete_size_product=product_name)
    keyboard = get_sizes_keyboard(sizes)
    await state.set_state(AdminState.waiting_delete_size_value)
    await message.answer(f"Выберите размер для удаления:", reply_markup=keyboard)

@dp.message(AdminState.waiting_delete_size_value, F.text.in_(["◀️ Назад", "❌ Выход"]))
async def admin_delete_size_value_nav(message: Message, state: FSMContext):
    if message.text == "❌ Выход":
        await state.clear()
        await show_admin_panel(message)
        return
    if message.text == "◀️ Назад":
        await state.set_state(AdminState.waiting_delete_size_product)
        products = get_all_products()
        keyboard = get_products_keyboard(products)
        await message.answer("Выберите товар:", reply_markup=keyboard)
        return

@dp.message(AdminState.waiting_delete_size_value)
async def admin_delete_size_confirm(message: Message, state: FSMContext):
    size = message.text.strip()
    data = await state.get_data()
    product_name = data.get("delete_size_product")
    if size not in get_sizes_of_product(product_name):
        await message.answer("❌ Такого размера нет.")
        return
    if delete_size(product_name, size):
        await message.answer(f"✅ Размер «{size}» удалён.")
    else:
        await message.answer("❌ Ошибка удаления.")
    await state.clear()
    await show_admin_panel(message)

# ---------- Показать все товары ----------
@dp.message(F.text == "📦 Все товары")
async def admin_all_products(message: Message):
    if not is_admin(message.from_user.id):
        return
    products = get_product_with_sizes_and_prices()
    if not products:
        await message.answer("Нет товаров.")
        return
    for name, sizes in products.items():
        text = f"<b>{name}</b>\n\n"
        for size, price in sizes.items():
            text += f"• {size} — {price} BYN\n"
        photos = get_product_photos(name)
        if photos:
            await message.answer_photo(photos[0], caption=text)
        else:
            await message.answer(text)

# ---------- Статистика ----------
@dp.message(F.text == "📊 Статистика")
async def admin_statistics(message: Message):
    if not is_admin(message.from_user.id):
        return
    total_orders = get_total_orders()
    total_revenue = get_total_revenue()
    top_products = get_top_products(5)
    top_sizes = get_top_sizes(5)

    stat_text = f"<b>📊 СТАТИСТИКА ПРОДАЖ</b>\n\n"
    stat_text += f"📦 Всего заказов: <b>{total_orders}</b>\n"
    stat_text += f"💰 Общая выручка: <b>{total_revenue} BYN</b>\n\n"
    stat_text += "<b>🏆 Самые продаваемые товары:</b>\n"
    if top_products:
        for i, (name, count) in enumerate(top_products, 1):
            stat_text += f"{i}. {name} — {count} шт.\n"
    else:
        stat_text += "Нет данных.\n"
    stat_text += "\n<b>👕 Самые продаваемые размеры:</b>\n"
    if top_sizes:
        for i, (size, count) in enumerate(top_sizes, 1):
            stat_text += f"{i}. {size} — {count} шт.\n"
    else:
        stat_text += "Нет данных.\n"
    await message.answer(stat_text)

# ---------- Режим покупателя ----------
@dp.message(F.text == "👤 Режим покупателя")
async def switch_to_customer(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("Переход в режим покупателя...", reply_markup=ReplyKeyboardRemove())
    if get_products_count() == 0:
        await message.answer("⚠️ Каталог пуст. Добавьте товары.")
        await show_admin_panel(message)
        return
    msg_id = await send_product_card(message.chat.id, 0)
    if msg_id:
        await state.update_data(catalog_message_id=msg_id, current_index=0)

# ---------- Отмена ----------
@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено", reply_markup=ReplyKeyboardRemove())
    if is_admin(message.from_user.id):
        await show_admin_panel(message)
    else:
        if get_products_count() > 0:
            msg_id = await send_product_card(message.chat.id, 0)
            if msg_id:
                await state.update_data(catalog_message_id=msg_id, current_index=0)

# ---------------------- ЗАПУСК ----------------------
async def main():
    logging.info("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())