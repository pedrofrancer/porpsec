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

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        raw = data["choices"][0]["message"]["content"].strip()
        return self._strip_thinking(raw)
