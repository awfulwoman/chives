from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    model: str = "llama3.2"
    api_key: str = "ollama"


class TelegramConfig(BaseModel):
    bot_token: str = ""
    allowed_chat_ids: list[int] = []


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CHIVES_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm: LLMConfig = LLMConfig()
    telegram: TelegramConfig = TelegramConfig()
    gateway_url: str = "http://127.0.0.1:4000/mcp"
    morning_brief_time: str = "08:00"
    event_reminder_minutes: int = 15
    idle_checkin_hours: int = 0
    state_path: str = "state"
    profile_path: str = "profile"
