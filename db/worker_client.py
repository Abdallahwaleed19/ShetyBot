"""
db/worker_client.py — HTTP client for Cloudflare Worker API.
Replaces SQLAlchemy/aiomysql — all DB operations go through the Worker.
"""
from __future__ import annotations
import logging
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
from config import WORKER_URL, WORKER_SECRET

logger = logging.getLogger(__name__)

# ── HTTP client (shared, async) ───────────────────────────────────────────────
_client: httpx.AsyncClient | None = None


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if WORKER_SECRET:
        h["Authorization"] = f"Bearer {WORKER_SECRET}"
    else:
        logger.warning(
            "WORKER_SECRET is empty — Cloudflare Worker will return 401. "
            "Set it in .env and `flyctl secrets set WORKER_SECRET=...`"
        )
    return h


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=WORKER_URL,
            timeout=8.0,
            headers=_headers(),
        )
    return _client


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()


# ── API helpers ───────────────────────────────────────────────────────────────

async def create_report(data: dict) -> dict:
    """POST /api/reports — Save a new sick leave report."""
    if not WORKER_SECRET:
        return {"success": False, "error": "WORKER_SECRET is not configured"}
    client = await get_client()
    try:
        resp = await client.post("/api/reports", json=data)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Worker create_report error: {e.response.text}")
        return {"success": False, "error": f"Worker HTTP {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Worker create_report exception: {e}")
        return {"success": False, "error": str(e)}


async def get_report(service_code: str) -> dict | None:
    """GET /api/reports/{service_code} — Fetch report by service code."""
    client = await get_client()
    try:
        resp = await client.get(f"/api/reports/{service_code}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        result = resp.json()
        return result.get("data")
    except Exception as e:
        logger.error(f"Worker get_report error: {e}")
        return None


async def search_by_national_id(national_id: str) -> list[dict]:
    """GET /api/reports?national_id=xxx — Search reports by national ID."""
    client = await get_client()
    try:
        resp = await client.get("/api/reports", params={"national_id": national_id})
        resp.raise_for_status()
        result = resp.json()
        return result.get("data", [])
    except Exception as e:
        logger.error(f"Worker search error: {e}")
        return []


async def upload_logo(filename: str, file_bytes: bytes, content_type: str = "image/jpeg") -> str | None:
    """POST /api/upload — Upload logo to R2, returns public URL."""
    if not WORKER_SECRET:
        logger.warning("Skipping R2 upload — WORKER_SECRET is not configured")
        return None
    client = await get_client()
    try:
        resp = await client.post(
            "/api/upload",
            content=file_bytes,
            params={"filename": filename},
            headers={**_headers(), "Content-Type": content_type},
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("url")
    except Exception as e:
        logger.error(f"Worker upload_logo error: {e}")
        return None


async def health_check() -> bool:
    """GET / — Check if Worker is reachable."""
    client = await get_client()
    try:
        resp = await client.get("/")
        return resp.status_code == 200
    except Exception:
        return False
