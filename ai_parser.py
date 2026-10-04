import json
import logging
import base64
from pathlib import Path
from typing import Union
from PIL import Image
from io import BytesIO

from config import settings
from models import MedicalReportExtraction, MedicationItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ти — професійний медичний асистент та експерт з аналізу рецептів і медичних висновків.
Твоє завдання — уважно проаналізувати надане зображення або текст консультативного висновку лікаря (українською мовою).

Витягни:
1. Спеціальність лікаря / клініку (наприклад: "Гастроентеролог, Оксфорд Медікал").
2. Діагноз (якщо вказано).
3. Загальні рекомендації з дієти / режиму (якщо вказано, наприклад "Здорове харчування, тарілка здорового харчування").
4. Перелік ВСІХ призначених ліків та препаратів:
   - name: точна назва препарату (наприклад: "Меверин (спарк)", "Мезим / Креон 10 000", "Дуфалак", "УДХК (урсіс, урсосан)")
   - dosage: дозування (наприклад: "1 капсула", "10-15 мл", "500 мг", "10 000")
   - frequency_per_day: кількість разів на день (число: 1, 2, 3 і т.д.)
   - timing_relation: зв'язок з прийомом їжі або розпорядком:
       * "before_meal" - до їди (наприклад за 20 хв до їди)
       * "with_meal" - під час їди
       * "after_meal" - після їди
       * "after_dinner" - після вечері
       * "bedtime" - перед сном
       * "throughout_day" - регулярний прийом протягом дня (краплі у ніс/очі/вуха, спреї, антибіотики тощо з частотою 2-6 р/д без прив'язки до їжі)
       * "as_needed" - ТІЛЬКИ якщо немає регулярної щоденної частоти і прийом виключно епізодичний/симптоматичний (наприклад "при болю", "за температури >38.5")
   - timing_offset_minutes: якщо зазначено час до/після їжі в хвилинах (наприклад 20 для "за 20 хв до їди"), інакше 0.
   - target_meals: список прийомів їжі (серед "breakfast", "lunch", "dinner").
       * Якщо 2 рази на день зазвичай це ["breakfast", "dinner"]
       * Якщо 3 рази на день: ["breakfast", "lunch", "dinner"]
       * Якщо 1 раз ввечері / після вечері: ["dinner"]
       * Якщо 1 раз зранку: ["breakfast"]
       * Якщо прийом протягом дня (краплі/спреї) або більше 3 разів: порожній список []
   - duration_days: тривалість курсу в днях (наприклад 14 для "2 тижні", 7 для "7 днів", якщо не вказано - null).
   - instructions: повний оригінальний текст інструкції до препарату.
   - notes: важливі застереження, зміни дози чи примітки (наприклад: "при збереженні закрепу", "через 2 тижні збільшити до 750мг після вечері").

Повертай відповідь СТРОГО у валідному форматі JSON згідно зі схемою MedicalReportExtraction.
"""

async def extract_medical_info(image_bytes: bytes = None, text_content: str = None) -> MedicalReportExtraction:
    # 1. Check Gemini
    if settings.GEMINI_API_KEY:
        try:
            return await _extract_with_gemini(image_bytes, text_content)
        except Exception as e:
            logger.warning(f"Спроба обробки через Gemini не вдалася: {e}")
            if not settings.OPENAI_API_KEY:
                raise

    # 2. Check OpenAI
    if settings.OPENAI_API_KEY:
        try:
            return await _extract_with_openai(image_bytes, text_content)
        except Exception as e:
            logger.error(f"Спроба обробки через OpenAI не вдалася: {e}")
            raise

    raise ValueError(
        "Не налаштовано робочий API ключ для ШІ-аналізу!\n"
        "Будь ласка, вкажіть GEMINI_API_KEY або OPENAI_API_KEY у файлі .env"
    )

async def _extract_with_gemini(image_bytes: bytes = None, text_content: str = None) -> MedicalReportExtraction:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    contents = [SYSTEM_PROMPT]
    if text_content:
        contents.append(f"Текст висновку:\n{text_content}")

    if image_bytes:
        image = Image.open(BytesIO(image_bytes))
        contents.append(image)

    # List of candidate models to try in order of priority
    models_to_try = [
        'gemini-3.6-flash',
        'gemini-3.7-flash',
        'gemini-3.8-flash',
        'gemini-flash-latest',
        'gemini-3.5-flash-lite',
        'gemini-3.5-flash'
    ]
    last_err = None
    for m in models_to_try:
        try:
            logger.info(f"Спроба розпізнавання моделлю: {m}...")
            response = client.models.generate_content(
                model=m,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MedicalReportExtraction,
                    temperature=0.1
                ),
            )
            data = json.loads(response.text)
            logger.info(f"Успішно розпізнано моделлю {m}!")
            return MedicalReportExtraction.model_validate(data)
        except Exception as ex:
            last_err = ex
            err_str = str(ex)
            logger.warning(f"Модель {m} повернула помилку: {err_str[:150]}")
            # If model is unavailable (503), not found (404), overloaded (429), try next candidate
            if any(code in err_str for code in ["503", "404", "429", "UNAVAILABLE", "NOT_FOUND", "RESOURCE_EXHAUSTED"]):
                continue
            raise ex

    if last_err:
        raise last_err

async def _extract_with_openai(image_bytes: bytes = None, text_content: str = None) -> MedicalReportExtraction:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    user_content = []
    if text_content:
        user_content.append({"type": "text", "text": f"Текст висновку:\n{text_content}"})

    if image_bytes:
        base64_img = base64.b64encode(image_bytes).decode("utf-8")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}
        })

    messages.append({"role": "user", "content": user_content})

    completion = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=messages,
        response_format=MedicalReportExtraction,
        temperature=0.1
    )

    return completion.choices[0].message.parsed
