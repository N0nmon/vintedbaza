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
    
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
