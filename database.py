import json
import aiosqlite
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from config import settings
from models import MedicationItem, MedicalReportExtraction

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    timezone TEXT DEFAULT 'Europe/Kyiv',
    breakfast_time TEXT DEFAULT '08:30',
    lunch_time TEXT DEFAULT '13:30',
    dinner_time TEXT DEFAULT '19:30',
    bedtime TEXT DEFAULT '22:30',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prescriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    doctor_info TEXT,
    diagnosis TEXT,
    diet_info TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    prescription_id INTEGER,
    name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    frequency_per_day INTEGER DEFAULT 1,
    timing_relation TEXT DEFAULT 'with_meal',
    timing_offset_minutes INTEGER DEFAULT 0,
    target_meals TEXT DEFAULT '["breakfast"]',
    duration_days INTEGER,
    start_date TEXT NOT NULL,
    end_date TEXT,
    instructions TEXT,
    notes TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    FOREIGN KEY(prescription_id) REFERENCES prescriptions(id)
);

CREATE TABLE IF NOT EXISTS reminder_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    medication_id INTEGER NOT NULL,
    scheduled_time TEXT NOT NULL,
    taken INTEGER DEFAULT 0,
    taken_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    FOREIGN KEY(medication_id) REFERENCES medications(id)
);
"""

class Database:
    def __init__(self, db_path: str = settings.DATABASE_PATH):
        self.db_path = db_path

    async def init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(CREATE_TABLES_SQL)
            await db.commit()

    async def get_or_create_user(self, user_id: int, username: str = "", first_name: str = "") -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = await cursor.fetchone()
            if not user:
                await db.execute(
                    "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                    (user_id, username, first_name)
                )
                await db.commit()
                cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                user = await cursor.fetchone()
            return dict(user)

    async def update_user_meals(self, user_id: int, breakfast: str, lunch: str, dinner: str, bedtime: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users 
                SET breakfast_time = ?, lunch_time = ?, dinner_time = ?, bedtime = ?
                WHERE user_id = ?
                """,
                (breakfast, lunch, dinner, bedtime, user_id)
            )
            await db.commit()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = await cursor.fetchone()
            return dict(user) if user else None

    async def save_prescription_with_meds(
        self,
        user_id: int,
        extraction: MedicalReportExtraction
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO prescriptions (user_id, doctor_info, diagnosis, diet_info)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, extraction.doctor_specialty, extraction.diagnosis, extraction.diet_recommendations)
            )
            prescription_id = cursor.lastrowid
            today = date.today()

            for med in extraction.medications:
                start_date_str = today.isoformat()
                end_date_str = None
                if med.duration_days:
                    end_date = today + timedelta(days=med.duration_days)
                    end_date_str = end_date.isoformat()

                await db.execute(
                    """
                    INSERT INTO medications (
                        user_id, prescription_id, name, dosage, frequency_per_day,
                        timing_relation, timing_offset_minutes, target_meals,
                        duration_days, start_date, end_date, instructions, notes, is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        user_id,
                        prescription_id,
                        med.name,
                        med.dosage,
                        med.frequency_per_day,
                        med.timing_relation,
                        med.timing_offset_minutes,
                        json.dumps(med.target_meals, ensure_ascii=False),
                        med.duration_days,
                        start_date_str,
                        end_date_str,
                        med.instructions,
                        med.notes
                    )
                )
            await db.commit()
            return prescription_id

    async def get_active_medications(self, user_id: int) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM medications WHERE user_id = ? AND is_active = 1 ORDER BY id ASC",
                (user_id,)
            )
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                item = dict(r)
                if item.get("target_meals"):
                    try:
                        item["target_meals"] = json.loads(item["target_meals"])
                    except Exception:
                        item["target_meals"] = []
                result.append(item)
            return result

    async def get_all_active_medications(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM medications WHERE is_active = 1")
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                item = dict(r)
                if item.get("target_meals"):
                    try:
                        item["target_meals"] = json.loads(item["target_meals"])
                    except Exception:
                        item["target_meals"] = []
                result.append(item)
            return result

    async def get_medication_by_id(self, med_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM medications WHERE id = ?", (med_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            if item.get("target_meals"):
                try:
                    item["target_meals"] = json.loads(item["target_meals"])
                except Exception:
                    item["target_meals"] = []
            return item

    async def set_medication_active(self, med_id: int, is_active: bool):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE medications SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, med_id)
            )
            await db.commit()

    async def log_medication_taken(self, user_id: int, med_id: int, scheduled_time: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO reminder_logs (user_id, medication_id, scheduled_time, taken, taken_at)
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                """,
                (user_id, med_id, scheduled_time)
            )
            await db.commit()

db = Database()
