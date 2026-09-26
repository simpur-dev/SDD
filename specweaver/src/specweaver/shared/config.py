from __future__ import annotations

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SeekDbSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 2881
    user: str = "root"
    password: SecretStr = SecretStr("")
    database: str = "specweaver"


class PowerContextSettings(BaseModel):
    base_url: str = "http://localhost:8000"
    token: SecretStr | None = None
    timeout: float = 10.0


class InferenceSettings(BaseModel):
    provider: str = "none"  # none | minimax | deepseek | qianwen
    api_key: SecretStr | None = None
    base_url: str = "https://api.minimax.chat/v1"
    model: str = "MiniMax-Text-01"
    embed_model: str = "embo-01"
    dim: int = 1536


class ServerSettings(BaseModel):
    transport: str = "stdio"  # stdio | http
    host: str = "127.0.0.1"
    port: int = 8765
    mcp_path: str = "/mcp"


class WorkspaceSettings(BaseModel):
    root: str = "."
    test_command: str = "pytest"
    default_branch: str = "master"


class ContextSettings(BaseModel):
    budget_bytes: int = 8000
    n_results: int = 20


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    seekdb: SeekDbSettings = SeekDbSettings()
    powercontext: PowerContextSettings = PowerContextSettings()
    inference: InferenceSettings = InferenceSettings()
    server: ServerSettings = ServerSettings()
    workspace: WorkspaceSettings = WorkspaceSettings()
    context: ContextSettings = ContextSettings()
