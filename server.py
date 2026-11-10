"""Bakaláři MCP server (read-only).

Vystavuje data z Bakalář API 3 jako MCP tools přes streamable HTTP.
Přihlašovací údaje k Bakalářům i MCP token jsou jen v env proměnných.
"""
import datetime as dt
import os
import threading
import time
from typing import Any, Optional

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

BASE = os.environ["BAKALARI_URL"].rstrip("/")  # např. https://bakalari.skola.cz
USERNAME = os.environ["BAKALARI_USER"]
PASSWORD = os.environ["BAKALARI_PASS"]
MCP_TOKEN = os.environ["MCP_AUTH_TOKEN"]
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

# Host header check (ochrana proti DNS rebindingu). Za reverzní proxy s vlastní doménou
# by výchozí nastavení vracelo 421, proto: ALLOWED_HOSTS="mcp.tvoje-domena.cz" zapne
# kontrolu jen pro tyhle hosty, bez něj je kontrola vypnutá (server chrání MCP_AUTH_TOKEN).
_allowed = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=bool(_allowed),
    allowed_hosts=_allowed + ["localhost:*", "127.0.0.1:*"],
    allowed_origins=["*"],
)

mcp = FastMCP("bakalari", stateless_http=True, transport_security=_security)


class BakalariClient:
    """Drží access token, sám ho obnovuje a při 401 se přihlásí znovu."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._access: Optional[str] = None
        self._refresh: Optional[str] = None
        self._expires_at: float = 0.0
        self._http = httpx.Client(timeout=20)

    def _store(self, data: dict) -> None:
        self._access = data["access_token"]
        self._refresh = data.get("refresh_token")
        self._expires_at = time.time() + int(data.get("expires_in", 3600)) - 60

    def _login(self) -> None:
        r = self._http.post(
            f"{BASE}/api/login",
            data={
                "client_id": "ANDR",
                "grant_type": "password",
                "username": USERNAME,
                "password": PASSWORD,
            },
        )
        r.raise_for_status()
        self._store(r.json())

    def _refresh_token(self) -> None:
        r = self._http.post(
            f"{BASE}/api/login",
            data={
                "client_id": "ANDR",
                "grant_type": "refresh_token",
                "refresh_token": self._refresh,
            },
        )
        r.raise_for_status()
        self._store(r.json())

    def _ensure_token(self) -> None:
        if self._access and time.time() < self._expires_at:
            return
        if self._refresh:
            try:
                self._refresh_token()
                return
            except httpx.HTTPError:
                pass
        self._login()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        with self._lock:
            self._ensure_token()
            for attempt in range(2):
                r = self._http.request(
                    method,
                    f"{BASE}{path}",
                    headers={"Authorization": f"Bearer {self._access}"},
                    **kwargs,
                )
                if r.status_code == 401 and attempt == 0:
                    self._login()
                    continue
                r.raise_for_status()
                return r.json()


bk = BakalariClient()


@mcp.tool()
def get_user_info() -> Any:
    """Základní info o přihlášeném žákovi (jméno, třída, škola)."""
    return bk.request("GET", "/api/3/user")


@mcp.tool()
def get_marks(subject: Optional[str] = None) -> Any:
    """Známky žáka. Volitelně filtr podle názvu předmětu (část názvu, bez diakritiky nemusí sedět)."""
    data = bk.request("GET", "/api/3/marks")
    if subject:
        needle = subject.lower()
        data["Subjects"] = [
            s
            for s in data.get("Subjects", [])
            if needle in s.get("Subject", {}).get("Name", "").lower()
            or needle in s.get("Subject", {}).get("Abbrev", "").lower()
        ]
    return data


@mcp.tool()
def get_timetable(date: Optional[str] = None) -> Any:
    """Aktuální rozvrh na týden obsahující dané datum (YYYY-MM-DD). Bez parametru dnešní týden."""
    d = date or dt.date.today().isoformat()
    return bk.request("GET", "/api/3/timetable/actual", params={"date": d})


@mcp.tool()
def get_permanent_timetable() -> Any:
    """Stálý rozvrh (bez změn a suplování)."""
    return bk.request("GET", "/api/3/timetable/permanent")


@mcp.tool()
def get_komens_received() -> Any:
    """Přijaté zprávy z Komens (od učitelů a školy)."""
    return bk.request("POST", "/api/3/komens/messages/received")


@mcp.tool()
def get_absence() -> Any:
    """Absence žáka (omluvené/neomluvené hodiny podle dnů a předmětů)."""
    return bk.request("GET", "/api/3/absence/student")


@mcp.tool()
def get_subjects() -> Any:
    """Seznam předmětů a učitelů."""
    return bk.request("GET", "/api/3/subjects")


class TokenAuth(BaseHTTPMiddleware):
    """Pustí jen požadavky s Bearer tokenem nebo ?token=..."""

    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return JSONResponse({"ok": True})
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token", "")
        if not supplied or supplied != MCP_TOKEN:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


app = mcp.streamable_http_app()
app.add_middleware(TokenAuth)

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
