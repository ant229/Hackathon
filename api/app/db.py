"""Thin Supabase (PostgREST) client. If SUPABASE_URL is not set, the API runs in stub mode."""
import os

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def live() -> bool:
    return bool(SUPABASE_URL and SERVICE_KEY)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=f"{SUPABASE_URL}/rest/v1",
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
        },
        timeout=10,
    )


def select(table: str, params: dict | None = None) -> list[dict]:
    with _client() as c:
        r = c.get(f"/{table}", params={"select": "*", **(params or {})})
        r.raise_for_status()
        return r.json()


def insert(table: str, rows: list[dict] | dict, returning: bool = True) -> list[dict]:
    with _client() as c:
        r = c.post(f"/{table}", json=rows,
                   headers={"Prefer": "return=representation" if returning else "return=minimal"})
        r.raise_for_status()
        return r.json() if returning else []


def delete(table: str, params: dict) -> None:
    with _client() as c:
        c.delete(f"/{table}", params=params).raise_for_status()


def rpc(fn: str, args: dict | None = None):
    with _client() as c:
        r = c.post(f"/rpc/{fn}", json=args or {})
        r.raise_for_status()
        return r.json()
