import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent.resolve()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    BOT_TOKEN: str = ""
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    TIMEZONE: str = "Europe/Kyiv"
    DATABASE_PATH: str = str(BASE_DIR / "med_bot.db")

settings = Settings()
