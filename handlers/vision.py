import html
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from io import BytesIO

from ai_parser import extract_medical_info
from database import db
from keyboards import get_main_menu_keyboard, get_prescription_confirm_keyboard
from scheduler import calculate_medication_times

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.text == "📷 Додати висновок")
async def prompt_add_report(message: Message):
    await message.answer(
        "📸 <b>Надішліть фотографію медичного висновку або рецепта.</b>\n\n"
        "💡 <i>Порада: переконайтеся, що текст та розділ «Рекомендовано / Призначення» чітко видно і не засвічено спалахом.</i>"
    )

def format_extraction_preview(extraction, user) -> str:
    lines = ["📋 <b>Результати аналізу висновку:</b>\n"]
    if extraction.doctor_specialty:
        lines.append(f"👨‍⚕️ <b>Лікар/Клініка:</b> {html.escape(extraction.doctor_specialty)}")
    if extraction.diagnosis:
        lines.append(f"🩺 <b>Діагноз:</b> {html.escape(extraction.diagnosis)}")
    if extraction.diet_recommendations:
        lines.append(f"🥗 <b>Дієта/Рекомендації:</b> {html.escape(extraction.diet_recommendations)}")

    lines.append("\n💊 <b>Знайдені медикаменти та розрахований час:</b>\n")
    if not extraction.medications:
        lines.append("⚠️ Препаратів у тексті не виявлено.")
    else:
        for idx, med in enumerate(extraction.medications, 1):
            med_dict = med.model_dump()
            times = calculate_medication_times(med_dict, user)
            times_str = ", ".join([f"<code>{html.escape(t)}</code>" for t in times]) if times else "за потребою"
            dur_str = f"{med.duration_days} днів" if med.duration_days else "тривалий прийом"

            med_name = html.escape(med.name)
            dosage = html.escape(med.dosage)
            instructions = html.escape(med.instructions)

            lines.append(
                f"{idx}. <b>{med_name}</b>\n"
                f"   • Доза: {dosage}\n"
                f"   • Розклад: {times_str}\n"
                f"   • Правило: {instructions}\n"
                f"   • Курс: {dur_str}"
            )
            if med.notes:
                notes_esc = html.escape(med.notes)
                lines.append(f"   • 💡 Примітка: <i>{notes_esc}</i>")
            lines.append("")

    return "\n".join(lines)

@router.message(F.photo)
async def handle_photo_report(message: Message, bot: Bot):
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.username or "", message.from_user.first_name or "")

    status_msg = await message.answer("🔍 <b>Аналізую медичний висновок за допомогою ШІ...</b> Зачекайте кілька секунд ⏳")

    try:
        photo = message.photo[-1]
        file_io = BytesIO()
        await bot.download(photo, destination=file_io)
        image_bytes = file_io.getvalue()

        extraction = await extract_medical_info(image_bytes=image_bytes)

        if not extraction.medications:
            await status_msg.edit_text(
                "⚠️ Не вдалося знайти медикаментозні призначення на цьому зображенні.\n"
                "Спробуйте надіслати більш чітке фото розділу «Призначено / Рекомендовано»."
            )
            return

        prescription_id = await db.save_prescription_with_meds(user_id, extraction)
        preview_text = format_extraction_preview(extraction, user)

        await status_msg.delete()
        await message.answer(
            preview_text,
            reply_markup=get_prescription_confirm_keyboard(prescription_id)
        )

    except ValueError as ve:
        await status_msg.edit_text(f"⚠️ {html.escape(str(ve))}")
    except Exception as e:
        logger.error(f"Error handling photo: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Виникла помилка під час аналізу висновку: {html.escape(str(e)[:200])}\n\n"
            "Спробуйте надіслати фото ще раз або перевірте якість знімка."
        )

@router.message(F.document)
async def handle_document_report(message: Message, bot: Bot):
    doc = message.document
    mime = doc.mime_type or ""
    if not (mime.startswith("image/") or "pdf" in mime):
        await message.answer("⚠️ Будь ласка, надішліть файл у форматі зображення (JPG, PNG) або фотографію.")
        return

    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.username or "", message.from_user.first_name or "")
    status_msg = await message.answer("🔍 <b>Аналізую файл висновку...</b> ⏳")

    try:
        file_io = BytesIO()
        await bot.download(doc, destination=file_io)
        image_bytes = file_io.getvalue()

        extraction = await extract_medical_info(image_bytes=image_bytes)
        if not extraction.medications:
            await status_msg.edit_text(
                "⚠️ Не вдалося знайти медикаментозні призначення у документі."
            )
            return

        prescription_id = await db.save_prescription_with_meds(user_id, extraction)
        preview_text = format_extraction_preview(extraction, user)

        await status_msg.delete()
        await message.answer(
            preview_text,
            reply_markup=get_prescription_confirm_keyboard(prescription_id)
        )
    except Exception as e:
        logger.error(f"Error handling document: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Помилка обробки файлу: {html.escape(str(e)[:200])}")

@router.callback_query(F.data.startswith("confirm_rx:"))
async def on_confirm_prescription(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🎉 <b>Нагадування успішно активовано!</b>\n\n"
        "Я буду надсилати вам повідомлення перед або під час кожного прийому ліків відповідно до вашого режиму дня.\n\n"
        "Переглянути активні ліки або змінити години можна у меню нижче.",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer("Активовано!")

@router.callback_query(F.data.startswith("cancel_rx:"))
async def on_cancel_prescription(callback: CallbackQuery):
    rx_id = int(callback.data.split(":")[1])
    import aiosqlite
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute("UPDATE medications SET is_active = 0 WHERE prescription_id = ?", (rx_id,))
        await conn.commit()

    await callback.message.edit_text("❌ Призначення скасовано. Нагадування не будуть приходити.")
    await callback.answer("Скасовано")
