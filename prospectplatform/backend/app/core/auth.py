"""Controle de acesso a API e as previas locais.

Com API_TOKEN definido: toda rota protegida exige o token (cabecalho X-API-Token ou cookie
pp_token, usado pelo iframe da previa). Sem token: so aceita cliente em loopback.
Atencao: tunel (cloudflared, ngrok) chega como 127.0.0.1; quem expuser por tunel precisa do token.
"""

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

PROTECTED_PREFIXES = ("/api/", "/preview/", "/docs", "/redoc", "/openapi.json")
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
COOKIE = "pp_token"


def _token_from(request: Request) -> str:
    return request.headers.get("x-api-token") or request.cookies.get(COOKIE) or ""


def is_authorized(request: Request) -> bool:
    expected = settings.API_TOKEN
    if expected:
        return hmac.compare_digest(_token_from(request).encode(), expected.encode())
    host = request.client.host if request.client else ""
    return host in LOOPBACK


class TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(PROTECTED_PREFIXES) and not is_authorized(request):
            detail = "Token invalido ou ausente" if settings.API_TOKEN else \
                "Acesso fora do localhost exige API_TOKEN no .env"
            return JSONResponse({"detail": detail}, status_code=401)
        return await call_next(request)
