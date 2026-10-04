import asyncio
import logging
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import settings
from database import db
from scheduler import MedicationScheduler
from handlers import common, meds, vision

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def main():
    if not settings.BOT_TOKEN:
        logger.error(
            "\n"
            "==========================================================\n"
            "⚠️ ПОМИЛКА: BOT_TOKEN не встановлено у файлі .env!\n"
            "Отримайте токен бота у @BotFather в Telegram та запишіть його:\n"
            "BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ\n"
            "==========================================================\n"
        )
        return

    logger.info("Ініціалізація бази даних...")
    await db.init_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    scheduler = MedicationScheduler(bot)
    meds.set_scheduler(scheduler)

    # Register routers
    dp.include_router(common.router)
    dp.include_router(meds.router)
    dp.include_router(vision.router)

    # Start background scheduler
    scheduler_task = asyncio.create_task(scheduler.start())

    # Ensure any previous webhook is deleted
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("Медичний бот запущено та готовий до роботи!")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.is_running = False
        scheduler_task.cancel()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений.")
