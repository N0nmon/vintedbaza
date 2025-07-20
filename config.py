from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    bot_token: str
    admin_id: int
    forwarding_group_id: int | None = None # Добавили ID группы (опционально)
    
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
