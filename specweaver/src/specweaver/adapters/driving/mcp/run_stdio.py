from __future__ import annotations

from ....shared.config import Settings
from .server import build_mcp


def main() -> None:
    settings = Settings()
    mcp = build_mcp(settings)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
