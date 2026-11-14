
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    ZOHO_QUICKML_URL: str | None = None
    ZOHO_QUICKML_KEY: SecretStr | None = None
    ZOHO_ACCESS_TOKEN: SecretStr | None = None
    ZOHO_CATALYST_ORG: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
