from __future__ import annotations

import asyncio

from ....shared import di


async def _amain() -> None:
    async with di.run() as app:
        await app.mcp.run_async(transport="stdio")


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
