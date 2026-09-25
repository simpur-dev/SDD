from __future__ import annotations

import asyncio

import pymysql

from ....shared.config import SeekDbSettings


async def check_seekdb(settings: SeekDbSettings) -> dict:
    """Lightweight connectivity/version probe (used by doctor)."""

    def _query() -> str:
        conn = pymysql.connect(
            host=settings.host,
            port=settings.port,
            user=settings.user,
            password=settings.password.get_secret_value(),
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                return str(cur.fetchone()[0])
        finally:
            conn.close()

    version = await asyncio.to_thread(_query)
    return {"name": "seekdb", "ok": True, "version": version}
