import asyncio
import logging
import sys
from datetime import datetime
from functools import wraps
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from database import (
    add_product, add_size, delete_size, get_all_products, 
    delete_product, get_product_with_sizes_and_prices,
    get_product_with_photo, save_order, get_orders_count, backup_db,
    get_top_products, get_top_sizes, get_sales_by_period  
)
from config import BOT_TOKEN, ADMIN_IDS
from aiogram.client.default import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode

# =========================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# =========================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# =========================
# ДЕКОРАТОР ДЛЯ ОБРАБОТКИ ОШИБОК
# =========================

def handle_errors(func):
    """Декоратор для обработки ошибок в хендлерах"""
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        try:
            return await func(message, *args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в {func.__name__}: {e}", exc_info=True)
            await message.answer(
                "❌ Произошла техническая ошибка.\n"
                "Пожалуйста, попробуйте позже или используйте /cancel\n"
                "Если ошибка повторяется, сообщите администратору."
            )
    return wrapper

# =========================
# ИНИЦИАЛИЗАЦИЯ БОТА
# =========================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)

dp = Dispatcher(storage=MemoryStorage())

# Функция проверки админа
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# =========================
# STATES
# =========================

class OrderState(StatesGroup):
    choosing_product = State()
    choosing_size = State()
    choosing_delivery = State()
    waiting_fio = State()
    waiting_address = State()
    waiting_phone = State()

class AdminState(StatesGroup):
    waiting_product_name = State()
    waiting_product_photo = State()
    waiting_size_product = State()
    waiting_size_value = State()
    waiting_size_price = State()
    confirm_delete = State()
    waiting_delete_size_product = State()
    waiting_delete_size_value = State()


# =========================
# START
# =========================

@dp.message(CommandStart())
@handle_errors
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    logger.info(f"Пользователь {user_id} запустил бота")
    
    if is_admin(user_id):
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Добавить товар")],
                [KeyboardButton(text="📏 Добавить размер"), KeyboardButton(text="🗑️ Удалить размер")],
                [KeyboardButton(text="🗑️ Удалить товар")],
                [KeyboardButton(text="📦 Все товары")],
                [KeyboardButton(text="📊 Статистика")],
                [KeyboardButton(text="👤 Режим покупателя")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "🔧 **АДМИН ПАНЕЛЬ**\n\n"
            "Выберите действие:\n\n"
            f"📊 Всего заказов: {get_orders_count()}",
            reply_markup=keyboard
        )
    else:
        await show_products(message, state)


# =========================
# СТАТИСТИКА ДЛЯ АДМИНА
# =========================

@dp.message(F.text == "📊 Статистика")
@handle_errors
async def admin_stats_menu(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📈 Общая статистика")],
            [KeyboardButton(text="🏆 Топ товаров")],
            [KeyboardButton(text="👟 Топ размеров")],
            [KeyboardButton(text="📅 За месяц"), KeyboardButton(text="📆 За всё время")],
            [KeyboardButton(text="🔙 Назад в админку")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "📊 **СТАТИСТИКА БОТА**\n\n"
        "Выберите, что хотите посмотреть:",
        reply_markup=keyboard
    )


@dp.message(F.text == "📈 Общая статистика")
@handle_errors
async def admin_stats_total(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    # Статистика за всё время
    all_time = get_sales_by_period(days=3650)  # ~10 лет
    
    if all_time:
        text = (
            f"📊 **ОБЩАЯ СТАТИСТИКА**\n\n"
            f"📦 Всего заказов: **{all_time['total_orders']}**\n"
            f"💰 Общая выручка: **{all_time['total_revenue']} BYN**\n"
            f"📊 Средний чек: **{all_time['avg_order_value']} BYN**\n"
            f"👥 Уникальных клиентов: **{all_time['unique_customers']}**\n"
        )
    else:
        text = "📊 Пока нет заказов для статистики."
    
    await message.answer(text)


@dp.message(F.text == "🏆 Топ товаров")
@handle_errors
async def admin_stats_top_products(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    top_products = get_top_products(limit=10)
    
    if not top_products:
        await message.answer("🏆 Пока нет продаж для составления топа.")
        return
    
    text = "🏆 **САМЫЕ ПРОДАВАЕМЫЕ ТОВАРЫ**\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, product in enumerate(top_products):
        medal = medals[i] if i < 3 else f"{i+1}."
        text += (
            f"{medal} **{product['name']}**\n"
            f"   📦 Продано: {product['orders_count']} шт.\n"
            f"   💰 Выручка: {product['total_revenue']} BYN\n"
            f"   📊 Средняя цена: {product['avg_price']} BYN\n\n"
        )
    
    # Разбиваем длинные сообщения
    if len(text) > 4000:
        await message.answer(text[:4000])
        await message.answer(text[4000:8000])
    else:
        await message.answer(text)


@dp.message(F.text == "👟 Топ размеров")
@handle_errors
async def admin_stats_top_sizes(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    top_sizes = get_top_sizes(limit=10)
    
    if not top_sizes:
        await message.answer("👟 Пока нет продаж для составления топа размеров.")
        return
    
    text = "👟 **САМЫЕ ХОДОВЫЕ РАЗМЕРЫ**\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, size_data in enumerate(top_sizes):
        medal = medals[i] if i < 3 else f"{i+1}."
        
        # Показываем популярные модели для этого размера
        products_text = ""
        if size_data['products']:
            products_text = f"   👟 Популярен у: {', '.join(size_data['products'][:2])}"
            if len(size_data['products']) > 2:
                products_text += f" и ещё {len(size_data['products']) - 2}"
        
        text += (
            f"{medal} **Размер {size_data['size']}**\n"
            f"   📦 Продано: {size_data['orders_count']} пар\n"
            f"   💰 Выручка: {size_data['total_revenue']} BYN\n"
            f"{products_text}\n\n"
        )
    
    if len(text) > 4000:
        await message.answer(text[:4000])
    else:
        await message.answer(text)


@dp.message(F.text == "📅 За месяц")
@handle_errors
async def admin_stats_month(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    monthly = get_sales_by_period(days=30)
    
    if monthly and monthly['total_orders'] > 0:
        text = (
            f"📅 **СТАТИСТИКА ЗА ПОСЛЕДНИЙ МЕСЯЦ**\n\n"
            f"📦 Заказов: **{monthly['total_orders']}**\n"
            f"💰 Выручка: **{monthly['total_revenue']} BYN**\n"
            f"📊 Средний чек: **{monthly['avg_order_value']} BYN**\n"
            f"👥 Клиентов: **{monthly['unique_customers']}**\n"
        )
        
        # Товары месяца
        top_monthly = get_top_products(limit=3, days=30)
        if top_monthly:
            text += "\n🏆 **Товары месяца:**\n"
            for i, p in enumerate(top_monthly[:3], 1):
                text += f"   {i}. {p['name']} — {p['orders_count']} шт.\n"
    else:
        text = "📅 За последний месяц заказов не было."
    
    await message.answer(text)


@dp.message(F.text == "📆 За всё время")
@handle_errors
async def admin_stats_all_time(message: Message):
    if not is_admin(message.from_user.id):
        return
    await admin_stats_total(message)  # Просто вызываем общую статистику


@dp.message(F.text == "🔙 Назад в админку")
@handle_errors
async def admin_back_to_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await show_admin_panel(message)


# =========================
# БЭКАП ДЛЯ АДМИНА
# =========================

@dp.message(Command("backup"))
@handle_errors
async def admin_backup(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    await message.answer("📀 Создаю резервную копию базы данных...")
    
    backup_path = backup_db()
    
    if backup_path:
        await message.answer(f"✅ Бэкап создан: `{backup_path}`", parse_mode="Markdown")
    else:
        await message.answer("❌ Не удалось создать бэкап. Проверьте логи.")


# =========================
# ПОКАЗ ТОВАРОВ (для покупателя)
# =========================

async def show_products(message: Message, state: FSMContext):
    """Показать список товаров"""
    try:
        products = get_product_with_sizes_and_prices()
        
        if not products:
            await message.answer("⚠️ Сейчас нет доступных товаров. Попробуйте позже.")
            return
        
        keyboard_buttons = []
        for product in products.keys():
            keyboard_buttons.append([KeyboardButton(text=product)])
        
        keyboard_buttons.append([KeyboardButton(text="🔙 Отменить заказ")])
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True,
            one_time_keyboard=False
        )
        
        await state.set_state(OrderState.choosing_product)
        
        await message.answer(
            "⚽ Добро пожаловать в 365football\n\nВыберите модель бутс:",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка в show_products: {e}")
        await message.answer("❌ Ошибка загрузки товаров. Попробуйте позже.")


# =========================
# PRODUCT (для покупателя)
# =========================

@dp.message(OrderState.choosing_product)
@handle_errors
async def product_handler(message: Message, state: FSMContext):
    if message.text == "🔙 Отменить заказ":
        await state.clear()
        await message.answer(
            "🗑️ Заказ отменён. Нажмите /start, чтобы начать заново.",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    product = message.text
    products = get_product_with_sizes_and_prices()
    
    if product not in products:
        await message.answer("❌ Выберите модель из списка.")
        return
    
    await state.update_data(product=product)
    sizes_data = products[product]
    
    if not sizes_data:
        await message.answer("⚠️ Для этого товара пока нет размеров.")
        await state.clear()
        return
    
    # Проверяем и обновляем фото при необходимости
    photo_file_id = get_product_with_photo(product)
    
    keyboard_buttons = []
    for size, price in sizes_data.items():
        button_text = f"{size} | {price} BYN"
        keyboard_buttons.append([KeyboardButton(text=button_text)])
    
    keyboard_buttons.append([KeyboardButton(text="🔙 Назад к товарам")])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    await state.set_state(OrderState.choosing_size)
    
    try:
        if photo_file_id:
            await message.answer_photo(
                photo=photo_file_id,
                caption=f"📦 **{product}**\n\nВыберите размер и цену:",
                reply_markup=keyboard
            )
        else:
            await message.answer(
                f"📦 **{product}**\n\nВыберите размер и цену:",
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке фото для {product}: {e}")
        await message.answer(
            f"📦 **{product}**\n\nВыберите размер и цену:",
            reply_markup=keyboard
        )


# =========================
# SIZE (для покупателя)
# =========================

@dp.message(OrderState.choosing_size)
@handle_errors
async def size_handler(message: Message, state: FSMContext):
    if message.text == "🔙 Назад к товарам":
        await show_products(message, state)
        return
    
    parts = message.text.split(" | ")
    if len(parts) != 2:
        await message.answer("❌ Пожалуйста, выберите размер из кнопок ниже.")
        return
    
    size = parts[0]
    price = parts[1].replace(" BYN", "")
    
    # Проверяем, что цена - число
    try:
        price_int = int(price)
    except ValueError:
        await message.answer("❌ Ошибка: некорректная цена. Пожалуйста, выберите размер заново.")
        return
    
    await state.update_data(size=size, price=price_int)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚚 Доставка")],
            [KeyboardButton(text="🏪 Самовывоз в Минске")],
            [KeyboardButton(text="🔙 Назад к размерам")]
        ],
        resize_keyboard=True
    )

    await state.set_state(OrderState.choosing_delivery)

    await message.answer(
        f"💰 Сумма заказа: **{price_int} BYN**\n\nВыберите способ получения:",
        reply_markup=keyboard
    )


# =========================
# DELIVERY (для покупателя)
# =========================

@dp.message(OrderState.choosing_delivery)
@handle_errors
async def delivery_handler(message: Message, state: FSMContext):
    if message.text == "🔙 Назад к размерам":
        data = await state.get_data()
        product = data.get("product")
        
        products = get_product_with_sizes_and_prices()
        sizes_data = products.get(product, {})
        
        if sizes_data:
            keyboard_buttons = []
            for size, price in sizes_data.items():
                button_text = f"{size} | {price} BYN"
                keyboard_buttons.append([KeyboardButton(text=button_text)])
            
            keyboard_buttons.append([KeyboardButton(text="🔙 Назад к товарам")])
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=keyboard_buttons,
                resize_keyboard=True,
                one_time_keyboard=False
            )
            
            await state.set_state(OrderState.choosing_size)
            
            photo_file_id = get_product_with_photo(product)
            if photo_file_id:
                try:
                    await message.answer_photo(
                        photo=photo_file_id,
                        caption=f"📦 **{product}**\n\nВыберите размер и цену:",
                        reply_markup=keyboard
                    )
                except:
                    await message.answer(
                        f"📦 **{product}**\n\nВыберите размер и цену:",
                        reply_markup=keyboard
                    )
            else:
                await message.answer(
                    f"📦 **{product}**\n\nВыберите размер и цену:",
                    reply_markup=keyboard
                )
        return
    
    delivery = message.text
    
    if delivery not in ["🚚 Доставка", "🏪 Самовывоз в Минске"]:
        await message.answer("❌ Пожалуйста, выберите способ получения из кнопок ниже.")
        return

    await state.update_data(delivery=delivery)

    if delivery == "🚚 Доставка":
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Назад к способам доставки")]],
            resize_keyboard=True
        )
        await state.set_state(OrderState.waiting_fio)
        await message.answer("📝 Введите ФИО:", reply_markup=keyboard)
        return

    data = await state.get_data()
    await send_order(message, state, data)


# =========================
# FIO, ADDRESS, PHONE
# =========================

@dp.message(OrderState.waiting_fio)
@handle_errors
async def fio_handler(message: Message, state: FSMContext):
    if message.text == "🔙 Назад к способам доставки":
        data = await state.get_data()
        price = data.get("price", "0")
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🚚 Доставка")],
                [KeyboardButton(text="🏪 Самовывоз в Минске")],
                [KeyboardButton(text="🔙 Назад к размерам")]
            ],
            resize_keyboard=True
        )
        
        await state.set_state(OrderState.choosing_delivery)
        await message.answer(
            f"💰 Сумма заказа: **{price} BYN**\n\nВыберите способ получения:",
            reply_markup=keyboard
        )
        return
    
    fio = message.text.strip()
    if len(fio) < 3:
        await message.answer("⚠️ Введите корректное ФИО (минимум 3 символа):")
        return
    
    if len(fio) > 200:
        await message.answer("⚠️ ФИО слишком длинное (максимум 200 символов):")
        return
    
    await state.update_data(fio=fio)
    await state.set_state(OrderState.waiting_address)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад к ФИО")]],
        resize_keyboard=True
    )
    await message.answer("🏠 Введите адрес Европочты:", reply_markup=keyboard)


@dp.message(OrderState.waiting_address)
@handle_errors
async def address_handler(message: Message, state: FSMContext):
    if message.text == "🔙 Назад к ФИО":
        await state.set_state(OrderState.waiting_fio)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Назад к способам доставки")]],
            resize_keyboard=True
        )
        await message.answer("📝 Введите ФИО:", reply_markup=keyboard)
        return
    
    address = message.text.strip()
    if len(address) < 5:
        await message.answer("⚠️ Введите корректный адрес (минимум 5 символов):")
        return
    
    if len(address) > 500:
        await message.answer("⚠️ Адрес слишком длинный (максимум 500 символов):")
        return
    
    await state.update_data(address=address)
    await state.set_state(OrderState.waiting_phone)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад к адресу")]],
        resize_keyboard=True
    )
    await message.answer("📞 Введите номер телефона:", reply_markup=keyboard)


@dp.message(OrderState.waiting_phone)
@handle_errors
async def phone_handler(message: Message, state: FSMContext):
    if message.text == "🔙 Назад к адресу":
        await state.set_state(OrderState.waiting_address)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Назад к ФИО")]],
            resize_keyboard=True
        )
        await message.answer("🏠 Введите адрес Европочты:", reply_markup=keyboard)
        return
    
    phone = message.text.strip()
    
    # Валидация телефона
    cleaned = phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    if not cleaned.isdigit() or len(cleaned) < 9 or len(cleaned) > 15:
        await message.answer("⚠️ Введите корректный номер телефона (например, +375291234567 или 80291234567):")
        return

    await state.update_data(phone=phone)
    data = await state.get_data()
    await send_order(message, state, data)


# =========================
# SEND ORDER
# =========================

async def send_order(message: Message, state: FSMContext, data: dict):
    product = data.get("product")
    size = data.get("size")
    price = data.get("price")
    delivery = data.get("delivery")
    fio = data.get("fio", "-")
    address = data.get("address", "-")
    phone = data.get("phone", "-")

    username = message.from_user.username
    user_id = message.from_user.id
    full_name = message.from_user.full_name

    user_link = f"@{username}" if username else "Нет username"
    
    # Сохраняем заказ в БД
    order_data = {
        'user_id': user_id,
        'user_name': full_name,
        'username': username,
        'product': product,
        'size': size,
        'price': price,
        'delivery': delivery,
        'fio': fio if delivery == "🚚 Доставка" else "-",
        'address': address if delivery == "🚚 Доставка" else "-",
        'phone': phone if delivery == "🚚 Доставка" else "-"
    }
    
    order_id = save_order(order_data)
    
    text = (
        f"🛒 НОВЫЙ ЗАКАЗ #{order_id if order_id else '?'}\n\n"
        f"👟 Модель: {product}\n"
        f"📏 Размер: {size}\n"
        f"💰 Цена: {price} BYN\n"
        f"🚚 Способ: {delivery}\n\n"
        f"👤 Клиент: {full_name}\n"
        f"📱 Username: {user_link}\n"
        f"🆔 ID: {user_id}\n\n"
    )

    if delivery == "🚚 Доставка":
        text += (
            f"📦 ФИО: {fio}\n"
            f"🏠 Адрес Европочты: {address}\n"
            f"📞 Телефон: {phone}\n"
        )

    photo = get_product_with_photo(product)
    
    # Отправляем всем админам
    for admin_id in ADMIN_IDS:
        try:
            if photo:
                await bot.send_photo(admin_id, photo=photo, caption=text)
            else:
                await bot.send_message(admin_id, text)
        except Exception as e:
            logger.error(f"Не удалось отправить заказ админу {admin_id}: {e}")
    
    await message.answer(
        f"✅ Заказ #{order_id if order_id else '?'} на сумму **{price} BYN** отправлен!\n"
        f"С вами свяжутся в ближайшее время! ✅\n\n"
        f"Нажмите /start для нового заказа",
        reply_markup=ReplyKeyboardRemove()
    )

    await state.clear()
    
    logger.info(f"Заказ #{order_id} от пользователя {user_id} успешно создан")


# =========================
# CANCEL
# =========================

@dp.message(Command("cancel"))
@handle_errors
async def cancel_handler(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("У вас нет активного заказа.")
    else:
        await state.clear()
        await message.answer(
            "🗑️ Заказ отменён. Нажмите /start, чтобы начать заново.",
            reply_markup=ReplyKeyboardRemove()
        )


# =========================
# АДМИН-ХЕНДЛЕРЫ
# =========================

@dp.message(F.text == "🗑️ Удалить размер")
@handle_errors
async def admin_delete_size_btn(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): 
        return
    
    products = get_all_products()
    if not products:
        return await message.answer("⚠️ Нет товаров с размерами.")
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=p)] for p in products],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await state.set_state(AdminState.waiting_delete_size_product)
    await message.answer("🗑️ Выберите товар, у которого нужно удалить размер:", reply_markup=keyboard)


@dp.message(StateFilter(AdminState.waiting_delete_size_product), F.text)
@handle_errors
async def admin_select_size_to_delete(message: Message, state: FSMContext):
    product = message.text
    products = get_product_with_sizes_and_prices()
    
    if product not in products:
        await message.answer("❌ Выберите товар из списка.")
        return
    
    sizes_data = products[product]
    if not sizes_data:
        await message.answer(f"⚠️ У товара **{product}** нет размеров для удаления.")
        await state.clear()
        await show_admin_panel(message)
        return
    
    await state.update_data(delete_product=product)
    
    keyboard_buttons = []
    for size, price in sizes_data.items():
        keyboard_buttons.append([KeyboardButton(text=f"{size} ({price} BYN)")])
    
    keyboard_buttons.append([KeyboardButton(text="🔙 Отмена")])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await state.set_state(AdminState.waiting_delete_size_value)
    await message.answer(
        f"🗑️ Удаление размера у **{product}**\n\nВыберите размер для удаления:",
        reply_markup=keyboard
    )


@dp.message(StateFilter(AdminState.waiting_delete_size_value), F.text)
@handle_errors
async def admin_confirm_delete_size(message: Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.clear()
        await show_admin_panel(message)
        return
    
    data = await state.get_data()
    product = data.get("delete_product")
    
    size_text = message.text.split(" (")[0]
    
    if delete_size(product, size_text):
        await message.answer(f"✅ Размер **{size_text}** удалён у товара **{product}**!")
    else:
        await message.answer(f"❌ Не удалось удалить размер **{size_text}**.")
    
    await state.clear()
    await show_admin_panel(message)


@dp.message(F.text == "➕ Добавить товар")
@handle_errors
async def admin_add_product_btn(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): 
        return
    await state.set_state(AdminState.waiting_product_name)
    await message.answer("📝 Введите **название** товара (например, Nike Mercurial 2025):")


@dp.message(StateFilter(AdminState.waiting_product_name), F.text)
@handle_errors
async def admin_waiting_photo(message: Message, state: FSMContext):
    await state.update_data(product_name=message.text.strip())
    await state.set_state(AdminState.waiting_product_photo)
    await message.answer("📸 Отправьте **фото** товара (можно как файл или как картинку):")


@dp.message(StateFilter(AdminState.waiting_product_photo), F.photo)
@handle_errors
async def admin_save_product_with_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    product_name = data.get("product_name")
    
    photo = message.photo[-1]
    file_id = photo.file_id
    
    if add_product(product_name, file_id):
        await message.answer(f"✅ Товар **{product_name}** успешно добавлен с фото!")
    else:
        await message.answer(f"⚠️ Товар **{product_name}** уже существует.")
    
    await state.clear()
    await show_admin_panel(message)


@dp.message(StateFilter(AdminState.waiting_product_photo))
@handle_errors
async def admin_photo_error(message: Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте **фото** (не файл и не текстовое сообщение):")


@dp.message(F.text == "📏 Добавить размер")
@handle_errors
async def admin_add_size_btn(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): 
        return
    products = get_all_products()
    if not products:
        return await message.answer("⚠️ Сначала добавьте товары!")
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=p)] for p in products],
        resize_keyboard=True, 
        one_time_keyboard=True
    )
    await state.set_state(AdminState.waiting_size_product)
    await message.answer("📦 Выберите товар, к которому добавить размер:", reply_markup=keyboard)


@dp.message(StateFilter(AdminState.waiting_size_product), F.text)
@handle_errors
async def admin_waiting_size_value(message: Message, state: FSMContext):
    await state.update_data(admin_product=message.text)
    await state.set_state(AdminState.waiting_size_value)
    await message.answer("📏 Введите **размер** (например, 42):")


@dp.message(StateFilter(AdminState.waiting_size_value), F.text)
@handle_errors
async def admin_waiting_price(message: Message, state: FSMContext):
    await state.update_data(admin_size=message.text.strip())
    await state.set_state(AdminState.waiting_size_price)
    await message.answer("💰 Введите **цену** в BYN (например, 199):")


@dp.message(StateFilter(AdminState.waiting_size_price), F.text)
@handle_errors
async def admin_save_size_with_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    data = await state.get_data()
    product = data.get("admin_product")
    size = data.get("admin_size")
    price = message.text.strip()
    
    try:
        price_int = int(price)
        if price_int <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число для цены (например, 199):")
        return
    
    if add_size(product, size, price_int):
        await message.answer(f"✅ Размер **{size}** по цене **{price_int} BYN** добавлен для **{product}**!")
    else:
        await message.answer(f"⚠️ Такой размер уже есть или товар не найден.")
    
    await state.clear()
    await show_admin_panel(message)


@dp.message(F.text == "🗑️ Удалить товар")
@handle_errors
async def admin_delete_btn(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): 
        return
    products = get_all_products()
    if not products:
        return await message.answer("⚠️ Нечего удалять.")
        
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=p)] for p in products],
        resize_keyboard=True, 
        one_time_keyboard=True
    )
    await state.set_state(AdminState.confirm_delete)
    await message.answer("⚠️ Выберите товар для удаления:", reply_markup=keyboard)


@dp.message(StateFilter(AdminState.confirm_delete), F.text)
@handle_errors
async def admin_do_delete(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    product = message.text
    if delete_product(product):
        await message.answer(f"🗑️ Товар **{product}** удалён.")
    else:
        await message.answer("❌ Ошибка при удалении.")
    
    await state.clear()
    await show_admin_panel(message)


@dp.message(F.text == "📦 Все товары")
@handle_errors
async def admin_list_products(message: Message):
    if not is_admin(message.from_user.id): 
        return
    
    products = get_product_with_sizes_and_prices()
    
    if not products:
        return await message.answer("📦 Список пуст.")
    
    for name, sizes in products.items():
        if sizes:
            sizes_text = "\n".join([f"  • {size} — {price} BYN" for size, price in sizes.items()])
            text = f"👟 **{name}**\n\n{sizes_text}"
        else:
            text = f"👟 **{name}**\n\nНет размеров"
        
        photo = get_product_with_photo(name)
        if photo:
            try:
                await message.answer_photo(photo=photo, caption=text)
            except:
                await message.answer(text)
        else:
            await message.answer(text)


@dp.message(F.text == "👤 Режим покупателя")
@handle_errors
async def admin_buyer_mode(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): 
        return
    await show_products(message, state)


async def show_admin_panel(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить товар")],
            [KeyboardButton(text="📏 Добавить размер"), KeyboardButton(text="🗑️ Удалить размер")],
            [KeyboardButton(text="🗑️ Удалить товар")],
            [KeyboardButton(text="📦 Все товары")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👤 Режим покупателя")]
        ], 
        resize_keyboard=True
    )
    await message.answer(
        "🔧 **АДМИН ПАНЕЛЬ**\n\n"
        f"📊 Всего заказов: {get_orders_count()}",
        reply_markup=keyboard
    )


# =========================
# FALLBACK HANDLER
# =========================

@dp.message(F.text)
@handle_errors
async def fallback_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    
    admin_states = [
        AdminState.waiting_product_name,
        AdminState.waiting_product_photo,
        AdminState.waiting_size_product,
        AdminState.waiting_size_value,
        AdminState.waiting_size_price,
        AdminState.confirm_delete,
        AdminState.waiting_delete_size_product,
        AdminState.waiting_delete_size_value
    ]
    
    if is_admin(message.from_user.id):
        if current_state in admin_states:
            return
        if current_state is None:
            await message.answer("🔧 Используйте кнопки админ-панели 👇")
            return
    
    if current_state is None:
        await message.answer("Нажмите /start чтобы начать заказ 👟")
    else:
        await message.answer("Пожалуйста, используйте кнопки ниже 👇\nИли /cancel для отмены.")


# =========================
# MAIN
# =========================

async def main():
    logger.info("=" * 50)
    logger.info("🤖 Бот запущен")
    logger.info(f"👑 Админы: {ADMIN_IDS}")
    logger.info("=" * 50)
    
    # Создаём бэкап при запуске
    backup_db()
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        raise
    finally:
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())