from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    bot_token: str
    admin_id: int
    forwarding_group_id: int | None = None
    
    pg_user: str
    pg_password: str
    pg_host: str
    pg_port: int = 5432
    pg_database: str

    db_user: str = Field(alias='DB_USER')
    db_pass: str = Field(alias='DB_PASS')
    db_host: str = Field(alias='DB_HOST')
    db_port: int = Field(alias='DB_PORT', default=5432)
    db_name: str = Field(alias='DB_NAME')
    
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
