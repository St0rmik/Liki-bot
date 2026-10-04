import html
from datetime import datetime, date
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from database import db
from keyboards import get_main_menu_keyboard, get_medication_detail_keyboard
from scheduler import calculate_medication_times

router = Router()

_scheduler_instance = None

def set_scheduler(scheduler):
    global _scheduler_instance
    _scheduler_instance = scheduler

@router.message(F.text == "📋 Мої активні ліки")
@router.message(Command("meds"))
async def list_active_medications(message: Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user:
        user = await db.get_or_create_user(user_id, message.from_user.username or "", message.from_user.first_name or "")

    meds = await db.get_active_medications(user_id)
    if not meds:
        await message.answer(
            "📭 У вас зараз немає активних призначень або нагадувань.\n\n"
            "Надішліть фото висновку лікаря, щоб додати ліки!",
            reply_markup=get_main_menu_keyboard()
        )
        return

    await message.answer(f"📋 <b>Ваші активні ліки ({len(meds)}):</b>")

    today = date.today()
    for med in meds:
        times = calculate_medication_times(med, user)
        times_str = ", ".join([f"<code>{html.escape(t)}</code>" for t in times]) if times else "за потребою / симптоматично"
        
        duration_info = "постійно або до особливого розпорядження"
        if med.get("end_date"):
            end_d = date.fromisoformat(med["end_date"])
            days_left = (end_d - today).days
            if days_left >= 0:
                duration_info = f"залишилось {days_left} дн. (до {end_d.strftime('%d.%m.%Y')})"
            else:
                duration_info = "курс завершено"

        med_name = html.escape(med.get("name") or "Препарат")
        dosage = html.escape(med.get("dosage") or "")
        instructions = html.escape(med.get("instructions") or "")

        text = (
            f"💊 <b>{med_name}</b>\n"
            f"🔹 Дозування: {dosage}\n"
            f"🕒 Години нагадувань: {times_str}\n"
            f"📋 Інструкція: {instructions}\n"
            f"⏳ Термін: {duration_info}"
        )
        if med.get("notes"):
            notes_esc = html.escape(med["notes"])
            text += f"\n💡 Примітка: <i>{notes_esc}</i>"

        await message.answer(text, reply_markup=get_medication_detail_keyboard(med["id"]))

@router.callback_query(F.data.startswith("taken:"))
async def on_taken_callback(callback: CallbackQuery):
    med_id = int(callback.data.split(":")[1])
    med = await db.get_medication_by_id(med_id)
    now_str = datetime.now().strftime("%H:%M")

    await db.log_medication_taken(callback.from_user.id, med_id, now_str)
    
    med_name = html.escape(med["name"] if med else "Препарат")
    await callback.message.edit_text(
        f"✅ <b>Прийом зафіксовано!</b>\n\n"
        f"💊 Препарат: <b>{med_name}</b>\n"
        f"🕒 Час: {now_str}\n\n"
        f"Чудово! Будьте здорові!"
    )
    await callback.answer("Прийом зафіксовано!")

@router.callback_query(F.data.startswith("snooze:"))
async def on_snooze_callback(callback: CallbackQuery):
    med_id = int(callback.data.split(":")[1])
    if _scheduler_instance:
        _scheduler_instance.add_snooze(callback.from_user.id, med_id, minutes=15)
    
    await callback.message.edit_text(
        "⏰ <b>Нагадування відкладено на 15 хвилин.</b>\n\n"
        "Я нагадаю вам ще раз незабаром!"
    )
    await callback.answer("Відкладено на 15 хв")

@router.callback_query(F.data.startswith("deactivate_med:"))
async def on_deactivate_med(callback: CallbackQuery):
    med_id = int(callback.data.split(":")[1])
    await db.set_medication_active(med_id, False)
    await callback.message.edit_text(
        "🗑 Препарат успішно вилучено з активних нагадувань."
    )
    await callback.answer("Вилучено")
