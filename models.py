from typing import List, Optional
from pydantic import BaseModel, Field

class MedicationItem(BaseModel):
    name: str = Field(description="Назва медикаменту (наприклад: 'Меверин (спарк)', 'Креон 10 000')")
    dosage: str = Field(description="Разове дозування (наприклад: '1 капсула', '10-15 мл', '500 мг')")
    frequency_per_day: int = Field(default=1, description="Кількість прийомів на день (наприклад: 1, 2, 3)")
    timing_relation: str = Field(
        default="with_meal",
        description="Зв'язок з їжею: 'before_meal' (до їди), 'with_meal' (під час їди), 'after_meal' (після їди), 'after_dinner' (після вечері), 'bedtime' (перед сном), 'as_needed' (при потребі/за збереження симптомів)"
    )
    timing_offset_minutes: int = Field(
        default=0,
        description="Кількість хвилин до або після їди (наприклад: 20 для 'за 20 хв до їди')"
    )
    target_meals: List[str] = Field(
        default_factory=lambda: ["breakfast"],
        description="Прийоми їжі: список з 'breakfast', 'lunch', 'dinner'"
    )
    duration_days: Optional[int] = Field(
        default=None,
        description="Тривалість курсу в днях (наприклад: 14 для 2 тижнів, 7 для 7 днів). Null якщо не вказано або постійно"
    )
    instructions: str = Field(
        description="Оригінальна або повна інструкція українською (наприклад: '1 капсула 2р/д за 20 хв до їди 2 тижні')"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Додаткові важливі примітки (наприклад: 'при збереженні закрепу', 'через 2 тижні збільшити до 750мг')"
    )

class MedicalReportExtraction(BaseModel):
    doctor_specialty: Optional[str] = Field(default=None, description="Спеціальність лікаря або назва клініки (наприклад: 'Гастроентеролог, Оксфорд Медікал')")
    diagnosis: Optional[str] = Field(default=None, description="Діагноз з висновку (якщо вказано)")
    diet_recommendations: Optional[str] = Field(default=None, description="Загальні рекомендації щодо дієти чи способу життя")
    medications: List[MedicationItem] = Field(default_factory=list, description="Список призначених медикаментів")
