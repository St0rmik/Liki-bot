import asyncio
import html
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database import db

logger = logging.getLogger(__name__)

def parse_time_str(time_str: str) -> tuple[int, int]:
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])

def calculate_medication_times(med: Dict[str, Any], user: Dict[str, Any]) -> List[str]:
    timing = med.get("timing_relation", "with_meal")
    offset = med.get("timing_offset_minutes", 0) or 0
    target_meals = med.get("target_meals", []) or []

    meal_times = {
        "breakfast": user.get("breakfast_time", "08:30"),
        "lunch": user.get("lunch_time", "13:30"),
        "dinner": user.get("dinner_time", "19:30"),
        "bedtime": user.get("bedtime", "22:30"),
    }

    if timing == "bedtime":
        return [meal_times["bedtime"]]

    if timing == "after_dinner":
        h, m = parse_time_str(meal_times["dinner"])
        add_m = offset if offset > 0 else 30
        dt = datetime(2026, 1, 1, h, m) + timedelta(minutes=add_m)
        return [dt.strftime("%H:%M")]

    calculated_times = []

    # If target_meals are specified and timing is related to meals
    if target_meals and timing in ("before_meal", "with_meal", "after_meal"):
        for meal in target_meals:
            if meal not in meal_times:
                continue
            h, m = parse_time_str(meal_times[meal])
            dt = datetime(2026, 1, 1, h, m)

            if timing == "before_meal":
                dt -= timedelta(minutes=offset if offset > 0 else 20)
            elif timing == "after_meal":
                dt += timedelta(minutes=offset if offset > 0 else 20)

            calculated_times.append(dt.strftime("%H:%M"))

    # If no meal times were calculated, but a daily frequency is set (e.g. drops, sprays, antibiotics without food relation)
    freq = med.get("frequency_per_day", 1) or 1
    if not calculated_times and freq > 0:
        # Distribute throughout wake hours (from breakfast to bedtime)
        b_h, b_m = parse_time_str(meal_times["breakfast"])
        s_h, s_m = parse_time_str(meal_times["bedtime"])
        start_min = b_h * 60 + b_m
        end_min = s_h * 60 + s_m

        if end_min <= start_min:
            end_min += 24 * 60

        if freq == 1:
            calculated_times = [meal_times["breakfast"]]
        elif freq == 2:
            calculated_times = [meal_times["breakfast"], meal_times["dinner"]]
        elif freq == 3:
            calculated_times = [meal_times["breakfast"], meal_times["lunch"], meal_times["dinner"]]
        else:
            # For 4, 5, 6 times/day: evenly space between breakfast and bedtime
            step = (end_min - start_min) / (freq - 1)
            for i in range(freq):
                total_m = int(start_min + i * step) % (24 * 60)
                cur_h = total_m // 60
                cur_m = (total_m % 60 // 5) * 5 # round to nearest 5 min
                calculated_times.append(f"{cur_h:02d}:{cur_m:02d}")

    return sorted(list(set(calculated_times)))

def get_reminder_keyboard(med_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Прийняв(ла)", callback_data=f"taken:{med_id}"),
                InlineKeyboardButton(text="⏰ Відкласти на 15 хв", callback_data=f"snooze:{med_id}")
            ]
        ]
    )

class MedicationScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.tz = ZoneInfo(settings.TIMEZONE)
        self.snoozed_reminders: List[Dict[str, Any]] = []
        self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("Планувальник нагадувань запущено.")
        while self.is_running:
            try:
                await self._check_reminders()
            except Exception as e:
                logger.error(f"Помилка в планувальнику нагадувань: {e}", exc_info=True)
            await asyncio.sleep(40)

    async def _check_reminders(self):
        now = datetime.now(self.tz)
        current_time_str = now.strftime("%H:%M")
        today_date = now.date()

        # 1. Process snoozed reminders
        pending_snoozes = []
        for item in self.snoozed_reminders:
            if now >= item["trigger_at"]:
                try:
                    med = await db.get_medication_by_id(item["med_id"])
                    if med and med["is_active"]:
                        med_name = html.escape(med.get("name") or "Препарат")
                        dosage = html.escape(med.get("dosage") or "")
                        instructions = html.escape(med.get("instructions") or "")

                        text = (
                            f"⏰ <b>Нагадування (відкладене)!</b>\n\n"
                            f"💊 Препарат: <b>{med_name}</b>\n"
                            f"🔹 Доза: {dosage}\n"
                            f"📝 Інструкція: {instructions}"
                        )
                        await self.bot.send_message(
                            chat_id=item["user_id"],
                            text=text,
                            reply_markup=get_reminder_keyboard(med["id"])
                        )
                except Exception as ex:
                    logger.error(f"Помилка відправки snoozed нагадування: {ex}")
            else:
                pending_snoozes.append(item)
        self.snoozed_reminders = pending_snoozes

        # 2. Check scheduled medications
        meds = await db.get_all_active_medications()
        for med in meds:
            if med.get("end_date"):
                end_d = date.fromisoformat(med["end_date"])
                if today_date > end_d:
                    await db.set_medication_active(med["id"], False)
                    med_name = html.escape(med.get("name") or "Препарат")
                    msg = (
                        f"🎉 <b>Курс прийому ліків завершено!</b>\n\n"
                        f"💊 Препарат: <b>{med_name}</b>\n"
                        f"🗓 Запланований термін прийому добіг кінця."
                    )
                    if med.get("notes"):
                        msg += f"\n\n⚠️ Зверніть увагу на примітку лікаря:\n<i>{html.escape(med['notes'])}</i>"
                    try:
                        await self.bot.send_message(chat_id=med["user_id"], text=msg)
                    except Exception:
                        pass
                    continue

            user = await db.get_user(med["user_id"])
            if not user:
                continue

            scheduled_times = calculate_medication_times(med, user)
            if current_time_str in scheduled_times:
                med_name = html.escape(med.get("name") or "Препарат")
                dosage = html.escape(med.get("dosage") or "")
                instructions = html.escape(med.get("instructions") or "")

                text = (
                    f"⏰ <b>Час прийому ліків!</b>\n\n"
                    f"💊 Препарат: <b>{med_name}</b>\n"
                    f"🔹 Дозування: <b>{dosage}</b>\n"
                    f"📋 Інструкція: {instructions}\n"
                )
                if med.get("notes"):
                    text += f"💡 Примітка: <i>{html.escape(med['notes'])}</i>\n"

                try:
                    await self.bot.send_message(
                        chat_id=med["user_id"],
                        text=text,
                        reply_markup=get_reminder_keyboard(med["id"])
                    )
                except Exception as ex:
                    logger.error(f"Не вдалося надіслати нагадування користувачу {med['user_id']}: {ex}")

    def add_snooze(self, user_id: int, med_id: int, minutes: int = 15):
        now = datetime.now(self.tz)
        trigger_at = now + timedelta(minutes=minutes)
        self.snoozed_reminders.append({
            "user_id": user_id,
            "med_id": med_id,
            "trigger_at": trigger_at
        })
