from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Мої активні ліки"), KeyboardButton(text="📷 Додати висновок")],
            [KeyboardButton(text="⚙️ Мій графік їжі"), KeyboardButton(text="ℹ️ Допомога / Інструкція")]
        ],
        resize_keyboard=True
    )

def get_prescription_confirm_keyboard(prescription_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Активувати всі нагадування", callback_data=f"confirm_rx:{prescription_id}"),
            ],
            [
                InlineKeyboardButton(text="❌ Скасувати", callback_data=f"cancel_rx:{prescription_id}")
            ]
        ]
    )

def get_medication_detail_keyboard(med_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Завершити / Видалити", callback_data=f"deactivate_med:{med_id}")
            ]
        ]
    )

def get_meal_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🍳 Сніданок (08:30)", callback_data="set_meal:breakfast"),
                InlineKeyboardButton(text="🍲 Обід (13:30)", callback_data="set_meal:lunch"),
            ],
            [
                InlineKeyboardButton(text="🥗 Вечеря (19:30)", callback_data="set_meal:dinner"),
                InlineKeyboardButton(text="🌙 Сон (22:30)", callback_data="set_meal:bedtime"),
            ],
            [
                InlineKeyboardButton(text="✏️ Змінити години", callback_data="edit_all_meals")
            ]
        ]
    )
