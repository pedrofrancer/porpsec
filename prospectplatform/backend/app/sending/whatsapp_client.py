import httpx
from app.core.config import settings


class WhatsAppClient:
    """Wrapper HTTP para o microserviço whatsapp-sender (Baileys)."""

    def __init__(self):
        self.base_url = settings.WHATSAPP_SENDER_URL.rstrip("/")

    async def get_status(self) -> dict:
        """Retorna status da conexão WhatsApp."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/status")
            resp.raise_for_status()
            return resp.json()

    async def is_connected(self) -> bool:
        """Verifica se o WhatsApp está conectado."""
        try:
            status = await self.get_status()
            return status.get("connected", False)
        except Exception:
            return False

    async def send(self, phone: str, message: str, extra_delay: int = 500, simulate_typing: bool = True) -> dict:
        """Envia mensagem via WhatsApp."""
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/send",
                json={
                    "phone": phone,
                    "message": message,
                    "extraDelay": extra_delay,
                    "simulateTyping": simulate_typing,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def pause(self) -> dict:
        """Pausa envios."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self.base_url}/pause")
            resp.raise_for_status()
            return resp.json()

    async def resume(self) -> dict:
        """Retoma envios."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self.base_url}/resume")
            resp.raise_for_status()
            return resp.json()
