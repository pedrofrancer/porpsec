import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import TokenAuthMiddleware


def make_client(client_host: str = "testclient") -> TestClient:
    app = FastAPI()
    app.add_middleware(TokenAuthMiddleware)

    @app.get("/api/v1/ping")
    def ping():
        return {"ok": True}

    @app.post("/api/v1/opt-out")
    def write():
        return {"ok": True}

    @app.get("/")
    def panel():
        return {"panel": True}

    return TestClient(app, client=(client_host, 50000))


@pytest.fixture
def token():
    with patch("app.core.auth.settings") as s:
        s.API_TOKEN = "s3cr3t"
        yield s


def test_without_token_setting_only_loopback_passes():
    with patch("app.core.auth.settings") as s:
        s.API_TOKEN = ""
        assert make_client("127.0.0.1").get("/api/v1/ping").status_code == 200
        remote = make_client("192.168.0.20").get("/api/v1/ping")
        assert remote.status_code == 401 and "API_TOKEN" in remote.json()["detail"]


def test_token_required_even_on_loopback(token):
    client = make_client("127.0.0.1")
    assert client.get("/api/v1/ping").status_code == 401
    assert client.post("/api/v1/opt-out", headers={"X-API-Token": "errado"}).status_code == 401
    assert client.post("/api/v1/opt-out", headers={"X-API-Token": "s3cr3t"}).status_code == 200


def test_cookie_works_for_preview_iframe(token):
    client = make_client("10.0.0.5")
    client.cookies.set("pp_token", "s3cr3t")
    assert client.get("/api/v1/ping").status_code == 200


def test_panel_html_is_public(token):
    assert make_client("10.0.0.5").get("/").status_code == 200
