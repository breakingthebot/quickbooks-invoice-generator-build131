"""
Configuration management for QuickBooks Online Invoicing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Application settings with environment variable fallback."""

    # QBO Mode & Credentials
    use_mock: bool = Field(default=True)
    environment: str = Field(default="sandbox")  # "sandbox" or "production"
    realm_id: str = Field(default="9341452019482710")
    client_id: str = Field(default="mock_client_id")
    client_secret: str = Field(default="mock_client_secret")
    access_token: str = Field(default="mock_access_token")
    refresh_token: str = Field(default="mock_refresh_token")
    webhook_verifier_token: str = Field(default="mock_webhook_verifier_token_xyz123")

    # API Endpoints
    sandbox_base_url: str = "https://sandbox-quickbooks.api.intuit.com"
    production_base_url: str = "https://quickbooks.api.intuit.com"

    # Local Storage
    database_path: str = Field(default="storage/qbo_invoicing.db")
    exports_dir: str = Field(default="storage/exports")

    # Invoicing Defaults
    default_payment_terms_days: int = Field(default=30)
    default_currency: str = Field(default="USD")
    default_tax_code: str = Field(default="TAX")
    default_item_ref: str = Field(default="1")

    @property
    def base_url(self) -> str:
        """Returns the appropriate API base URL."""
        if self.environment.lower() == "production":
            return self.production_base_url
        return self.sandbox_base_url

    @property
    def api_url(self) -> str:
        """Constructs the base company URL for QBO Accounting API v3."""
        return f"{self.base_url}/v3/company/{self.realm_id}"

    @classmethod
    def load(cls, env_path: Optional[str | Path] = None) -> Settings:
        """Load settings from environment variables or .env file."""
        if env_path and Path(env_path).exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("\"'")
                        if k not in os.environ:
                            os.environ[k] = v

        use_mock = os.getenv("QBO_USE_MOCK", "true").lower() in ("1", "true", "yes")
        env = os.getenv("QBO_ENVIRONMENT", "sandbox")
        realm_id = os.getenv("QBO_REALM_ID", "9341452019482710")
        client_id = os.getenv("QBO_CLIENT_ID", "mock_client_id")
        client_secret = os.getenv("QBO_CLIENT_SECRET", "mock_client_secret")
        access_token = os.getenv("QBO_ACCESS_TOKEN", "mock_access_token")
        refresh_token = os.getenv("QBO_REFRESH_TOKEN", "mock_refresh_token")
        verifier_token = os.getenv("QBO_WEBHOOK_VERIFIER_TOKEN", "mock_webhook_verifier_token_xyz123")

        db_path = os.getenv("DATABASE_PATH", "storage/qbo_invoicing.db")
        exports_dir = os.getenv("EXPORTS_DIR", "storage/exports")
        terms_days = int(os.getenv("DEFAULT_PAYMENT_TERMS_DAYS", "30"))
        currency = os.getenv("DEFAULT_CURRENCY", "USD")

        return cls(
            use_mock=use_mock,
            environment=env,
            realm_id=realm_id,
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            webhook_verifier_token=verifier_token,
            database_path=db_path,
            exports_dir=exports_dir,
            default_payment_terms_days=terms_days,
            default_currency=currency,
        )


# Global default settings instance
settings = Settings.load()
