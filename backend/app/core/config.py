from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "deplyx"
    env: str = "development"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "deplyxneo4j"

    postgres_host: str = "postgres"
    postgres_db: str = "deplyx"
    postgres_user: str = "deplyx"
    postgres_password: str = "deplyx"
    postgres_port: int = 5432

    redis_url: str = "redis://redis:6379/0"
    approval_timeout_hours: int = 48
    cors_allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    gemini_api_key: str = ""

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value):
        if isinstance(value, str):
            if value.strip() == "":
                return []
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.env.strip().lower() in {"production", "prod"} and self.jwt_secret_key == "change-me":
            raise ValueError("JWT_SECRET_KEY must be set to a secure value in production")
        return self

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
