import asyncio
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from database import Database
from models import MedicalReportExtraction, MedicationItem
from scheduler import calculate_medication_times

TEST_DB_PATH = "test_med_bot.db"

async def run_tests():
    print("--- 1. Testing Database & Models ---")
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    test_db = Database(TEST_DB_PATH)
    await test_db.init_db()

    user = await test_db.get_or_create_user(123456, "testuser", "TestUser")
    print(f"User created: {user['username']}, Breakfast: {user['breakfast_time']}")

    mock_extraction = MedicalReportExtraction(
        doctor_specialty="Гастроентеролог, Оксфорд Медікал",
        diagnosis="ЖКХ, прекам'яна стадія",
        diet_recommendations="Здорове харчування, тарілка здорового харчування",
        medications=[
            MedicationItem(
                name="Меверин (спарк)",
                dosage="1 капс",
                frequency_per_day=2,
                timing_relation="before_meal",
                timing_offset_minutes=20,
                target_meals=["breakfast", "dinner"],
                duration_days=14,
                instructions="1х2р/д за 20 хв до їди 2 тижні"
            ),
            MedicationItem(
                name="Мезим / Креон 10 000",
                dosage="1 капсула",
                frequency_per_day=3,
                timing_relation="with_meal",
                timing_offset_minutes=0,
                target_meals=["breakfast", "lunch", "dinner"],
                duration_days=7,
                instructions="10 000 1х3р/д під час їди 7 днів"
            ),
            MedicationItem(
                name="Дуфалак",
                dosage="10-15 мл",
                frequency_per_day=1,
                timing_relation="as_needed",
                timing_offset_minutes=0,
                target_meals=[],
                duration_days=None,
                instructions="10-15мл 1-2р/д (при збереженні закрепу)",
                notes="при збереженні закрепу"
            ),
            MedicationItem(
                name="УДХК (урсіс, урсосан)",
                dosage="500 мг",
                frequency_per_day=1,
                timing_relation="after_dinner",
                timing_offset_minutes=30,
                target_meals=["dinner"],
                duration_days=14,
                instructions="500мг після вечері 2 тижні, збільшити до 750мг",
                notes="через 2 тижні збільшити до 750мг після вечері, контроль УЗД ОЧП"
            )
        ]
    )

    rx_id = await test_db.save_prescription_with_meds(123456, mock_extraction)
    print(f"Saved prescription ID: {rx_id}")

    meds = await test_db.get_active_medications(123456)
    print(f"Retrieved {len(meds)} active medications:")
    for m in meds:
        times = calculate_medication_times(m, user)
        print(f" - {m['name']} -> нагадування о {times} (правило: {m['instructions']})")

    assert len(meds) == 4

    # Meverin: breakfast (08:30 - 20min = 08:10), dinner (19:30 - 20min = 19:10)
    meverin_times = calculate_medication_times(meds[0], user)
    assert meverin_times == ["08:10", "19:10"], f"Unexpected Meverin times: {meverin_times}"

    # Mezim: breakfast 08:30, lunch 13:30, dinner 19:30
    mezim_times = calculate_medication_times(meds[1], user)
    assert mezim_times == ["08:30", "13:30", "19:30"], f"Unexpected Mezim times: {mezim_times}"

    # Dufalac: as_needed
    dufalac_times = calculate_medication_times(meds[2], user)
    assert dufalac_times == [], f"Unexpected Dufalac times: {dufalac_times}"

    # UDHQ: after dinner (19:30 + 30min = 20:00)
    udhq_times = calculate_medication_times(meds[3], user)
    assert udhq_times == ["20:00"], f"Unexpected UDHQ times: {udhq_times}"

    # Cleanup test db
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    print("All unit tests and schedule calculations passed successfully! [OK]")

if __name__ == "__main__":
    asyncio.run(run_tests())
