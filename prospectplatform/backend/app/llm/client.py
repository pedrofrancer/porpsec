import asyncio
import re

import httpx
from app.core.config import settings


class LLMClient:
    """Cliente para provedores OpenAI-compatible (qualquer BASE_URL + API_KEY)."""

    def __init__(self):
        self.base_url = settings.LLM_BASE_URL.rstrip("/")
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _strip_thinking(self, text: str) -> str:
        """Remove bloco <think>...</think> de modelos Qwen."""
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        return cleaned.strip()

    async def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        """Envia mensagem ao LLM e retorna a resposta como string."""
        if not self.is_configured:
            raise ValueError("LLM nao configurado. Defina LLM_API_KEY no .env")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }

        data = await self._post_with_retry(headers, payload)

        raw = data["choices"][0]["message"]["content"].strip()
        return self._strip_thinking(raw)

    RETRY_STATUS = {429, 500, 502, 503, 504}
    MAX_ATTEMPTS = 4

    async def _post_with_retry(self, headers: dict, payload: dict) -> dict:
        """Groq free tier devolve 429 com frequencia: espera (Retry-After ou backoff) e tenta de novo."""
        delay = 2.0
        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(1, self.MAX_ATTEMPTS + 1):
                resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                if resp.status_code not in self.RETRY_STATUS or attempt == self.MAX_ATTEMPTS:
                    resp.raise_for_status()
                    return resp.json()
                retry_after = resp.headers.get("retry-after")
                wait = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else delay
                await asyncio.sleep(min(wait, 60))
                delay *= 2
