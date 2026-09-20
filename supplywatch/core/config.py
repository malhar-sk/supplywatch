from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SupplyWatch"
    app_version: str = "0.1.0"
    env: str = "dev"
    database_url: str
    resend_api_key: str = ""
    resend_from_email: str = "alerts@supplywatch.local"
    enable_scheduler: bool = True
    default_rate_limit_free: int = 100
    # Optional free-tier price-data fallbacks (used only if yfinance returns
    # nothing usable). Both are no-ops when left blank -- see ingest/usgs.py.
    twelvedata_api_key: str = ""
    finnhub_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
