from __future__ import annotations

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from utils.env_loader import get_env


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def generate_chat_completion(prompt: str, system: str, max_tokens: int = 300) -> str:
    key = get_env("OPENAI_API_KEY")
    if not key or key.lower().startswith("your"):
        raise ValueError("OpenAI API key not configured")

    client = OpenAI(api_key=key)
    model = get_env("OPENAI_MODEL", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise ValueError("Empty OpenAI response")
    return text
