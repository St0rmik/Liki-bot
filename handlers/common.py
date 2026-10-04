import html
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from keyboards import get_main_menu_keyboard, get_meal_settings_keyboard

router = Router()

class MealSettingsState(StatesGroup):
    waiting_for_meals = State()

@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await db.get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        first_name=message.from_user.first_name or ""
    )
    first_name_esc = html.escape(message.from_user.first_name or "користувачу")
    
    welcome_text = (
        f"👋 Вітаю, <b>{first_name_esc}</b>!\n\n"
        f"Я — ваш персональний медичний асистент для контролю прийому ліків 🩺\n\n"
        f"📸 <b>Як це працює?</b>\n"
        f"1. Сфотографуйте або надішліть фото висновку лікаря (консультативний висновок, рецепт).\n"
        f"2. Штучний інтелект розпізнає всі призначені ліки, дозування, схему прийому (до їди, після, кількість днів).\n"
        f"3. Я розрахую точний час нагадувань згідно з вашим режимом дня і щоденно надсилатиму сповіщення.\n\n"
        f"🕒 <b>Ваш поточний графік дня:</b>\n"
        f"🍳 Сніданок: <code>{html.escape(user['breakfast_time'])}</code>\n"
        f"🍲 Обід: <code>{html.escape(user['lunch_time'])}</code>\n"
        f"🥗 Вечеря: <code>{html.escape(user['dinner_time'])}</code>\n"
        f"🌙 Сон: <code>{html.escape(user['bedtime'])}</code>\n\n"
        f"Ви можете змінити години у меню <b>⚙️ Мій графік їжі</b>.\n"
        f"Надішліть фото висновку, щоб розпочати!"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu_keyboard())

@router.message(F.text == "ℹ️ Допомога / Інструкція")
@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📖 <b>Інструкція користувача:</b>\n\n"
        "🔹 <b>Як додати ліки:</b>\n"
        "Просто надішліть фотографію медичного висновку або напишіть текст призначення у повідомленні.\n\n"
        "🔹 <b>Як розраховується час:</b>\n"
        "• «за 20 хв до їди» — надсилається за 20 хв до вашого сніданку/вечері.\n"
        "• «під час їди» — надсилається о годині прийому їжі.\n"
        "• «після вечері» — через 30 хв після вашої вечері.\n"
        "• «перед сном» — за 15 хв до вашого сну.\n\n"
        "🔹 <b>Нагадування:</b>\n"
        "Коли надходить сповіщення, ви можете натиснути:\n"
        "• <code>✅ Прийняв(ла)</code> — фіксує виконання.\n"
        "• <code>⏰ Відкласти на 15 хв</code> — нагадає повторно через 15 хвилин.\n\n"
        "🔹 <b>Керування:</b>\n"
        "• <b>📋 Мої активні ліки</b> — перелік призначених курсів та можливість достроково припинити прийом."
    )
    await message.answer(help_text, reply_markup=get_main_menu_keyboard())

@router.message(F.text == "⚙️ Мій графік їжі")
@router.message(Command("schedule"))
async def show_schedule(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        user = await db.get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    text = (
        "⚙️ <b>Ваш поточний графік дня:</b>\n\n"
        f"🍳 <b>Сніданок:</b> <code>{html.escape(user['breakfast_time'])}</code>\n"
        f"🍲 <b>Обід:</b> <code>{html.escape(user['lunch_time'])}</code>\n"
        f"🥗 <b>Вечеря:</b> <code>{html.escape(user['dinner_time'])}</code>\n"
        f"🌙 <b>Час сну:</b> <code>{html.escape(user['bedtime'])}</code>\n\n"
        "Усі нагадування прив'язані до цього розкладу.\n"
        "Бажаєте змінити години? Натисніть кнопку нижче 👇"
    )
    await message.answer(text, reply_markup=get_meal_settings_keyboard())

@router.callback_query(F.data == "edit_all_meals")
async def edit_meals_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MealSettingsState.waiting_for_meals)
    await callback.message.answer(
        "📝 Надішліть новий графік 4 числами через кому або пробіл у форматі <code>ГГ:ХХ</code>:\n\n"
        "<b>Приклад:</b> <code>08:00, 13:00, 19:00, 23:00</code>\n"
        "(Сніданок, Обід, Вечеря, Сон)"
    )
    await callback.answer()

@router.message(MealSettingsState.waiting_for_meals)
async def process_new_meals(message: Message, state: FSMContext):
    raw = message.text.replace(",", " ").replace(";", " ")
    parts = [p.strip() for p in raw.split() if p.strip()]
    if len(parts) != 4:
        await message.answer(
            "⚠️ Будь ласка, введіть рівно 4 значення часу у форматі <code>HH:MM</code>, розділені пробілами чи комами.\n"
            "Приклад: <code>08:30 13:30 19:30 22:30</code>"
        )
        return
    
    b, l, d, s = parts[0], parts[1], parts[2], parts[3]
    await db.update_user_meals(message.from_user.id, b, l, d, s)
    await state.clear()
    
    await message.answer(
        f"✅ <b>Розклад успішно оновлено!</b>\n\n"
        f"🍳 Сніданок: <code>{html.escape(b)}</code>\n"
        f"🍲 Обід: <code>{html.escape(l)}</code>\n"
        f"🥗 Вечеря: <code>{html.escape(d)}</code>\n"
        f"🌙 Сон: <code>{html.escape(s)}</code>\n\n"
        f"Час нагадувань автоматично перераховано.",
        reply_markup=get_main_menu_keyboard()
    )
