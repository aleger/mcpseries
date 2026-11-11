"""Tracker credentials and IDs. One parser (pydantic-settings, python-dotenv syntax) everywhere.
Real environment variables win over .env.local. Never print or log these values."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from delivery_mcp.config import ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT / ".env", ROOT / ".env.local"), extra="ignore")

    clickup_api_token: SecretStr | None = None
    clickup_workspace_id: str | None = None
    clickup_space_id: str | None = None
    ado_org: str | None = None
    ado_project: str | None = None
    ado_pat: SecretStr | None = None
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_client_secret: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
