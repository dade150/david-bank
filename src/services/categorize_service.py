import instructor
from openai import AsyncOpenAI

from src.config import settings
from src.types.categorize import CategorizeRequest, CategorizeResponse

CATEGORIZE_SYSTEM = """You are an expert at categorizing Italian bank transactions.

Categories:
- UTILITIES (luce, gas, acqua, internet, telefono)
- GROCERIES (supermercati, alimentari, market)
- TRANSPORT (carburante, treno, mezzi, parcheggi)
- RESTAURANTS (ristoranti, bar, fast food)
- ENTERTAINMENT (cinema, palestra, abbonamenti streaming)
- OTHER (tutto il resto)

Subcategory: specifica più precisa in italiano (es. "ENERGY", "SUPERMARKET", "FUEL").
Confidence: tua sicurezza 0.0-1.0.
Reasoning: 1-2 frasi spiegando la scelta.
"""

client = instructor.from_openai(AsyncOpenAI(api_key=settings.openai_api_key))


async def categorize(req: CategorizeRequest) -> CategorizeResponse:
    return await client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=CategorizeResponse,
        messages=[
            {"role": "system", "content": CATEGORIZE_SYSTEM},
            {
                "role": "user",
                "content": f"Description: {req.description}\nAmount: €{req.amount} {req.currency}",
            },
        ],
        max_retries=2,
        temperature=0.9,
    )
