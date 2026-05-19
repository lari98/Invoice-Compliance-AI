"""
Application configuration using pydantic-settings.
Values are loaded from environment variables / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Swiss Invoice Compliance AI"
    app_version: str = "1.5.0"
    debug: bool = False

    database_url: str = "sqlite:///./swiss_invoices.db"

    upload_dir: Path = Path("./uploads")
    export_dir: Path = Path("./exports")
    max_upload_size_mb: int = 20

    ocr_engine: str = "enterprise"
    tesseract_cmd: str = ""
    tesseract_languages: str = "deu+fra+ita+eng"

    # 30 fiat + 5 crypto by default
    accepted_currencies: str = (
        "CHF,EUR,USD,GBP,CAD,JPY,SGD,RUB,AUD,AED,CNY,KRW,INR,BRL,HKD,"
        "NOK,SEK,DKK,NZD,ZAR,TRY,THB,PLN,SAR,MYR,MXN,CZK,HUF,ILS,PHP,"
        "IDR,TWD,EGP,NGN,UAH,BTC,ETH,USDT,BNB,XRP"
    )
    api_key: str = "changeme-in-production"

    @property
    def accepted_currencies_list(self) -> list[str]:
        return [c.strip() for c in self.accepted_currencies.split(",")]


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.export_dir.mkdir(parents=True, exist_ok=True)
