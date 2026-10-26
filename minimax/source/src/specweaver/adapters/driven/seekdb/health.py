from __future__ import annotations

import asyncio

import pymysql

from ....shared.config import SeekDbSettings
from ....shared.errors import BackendConnectionError


async def check_seekdb(settings: SeekDbSettings) -> dict:
    """Lightweight connectivity/version probe (used by doctor).

    Failures surface as the documented adapter error contract rather than raw
    pymysql exceptions, so a caller that reports on backends never has to know
    which driver produced the outage.
    """

    def _connect():
        try:
            return pymysql.connect(
                host=settings.host,
                port=settings.port,
                user=settings.user,
                password=settings.password.get_secret_value(),
                connect_timeout=5,
                read_timeout=10,
                write_timeout=10,
            )
        except pymysql.Error as exc:
            raise BackendConnectionError(
                f"seekdb unreachable at {settings.host}:{settings.port}: {exc}"
            ) from exc

    def _query() -> str:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                return str(cur.fetchone()[0])
        except pymysql.Error as exc:
            raise BackendConnectionError(
                f"seekdb version() failed: {exc}"
            ) from exc
        finally:
            conn.close()

    version = await asyncio.to_thread(_query)
    return {"name": "seekdb", "ok": True, "version": version}
