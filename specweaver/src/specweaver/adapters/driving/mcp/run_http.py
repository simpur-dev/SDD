from __future__ import annotations

import uvicorn

from ....shared.config import Settings
from .server import build_mcp


def main() -> None:
    settings = Settings()
    mcp = build_mcp(settings)
    app = mcp.http_app(path=settings.server.mcp_path)
    uvicorn.run(app, host=settings.server.host, port=settings.server.port)


if __name__ == "__main__":
    main()
