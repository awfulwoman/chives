from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class LLMConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    model: str = "llama3.2"
    api_key: str = "ollama"


class TelegramConfig(BaseModel):
    bot_token: str = ""
    allowed_chat_ids: List[int] = []


class IMAPConfig(BaseModel):
    host: str = ""
    port: int = 993
    username: str = ""
    password: str = ""


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CHIVES_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    llm: LLMConfig = LLMConfig()
    telegram: TelegramConfig = TelegramConfig()
    imap: IMAPConfig = IMAPConfig()
    morning_brief_time: str = "08:00"
    event_reminder_minutes: int = 15
    idle_checkin_hours: int = 0
    state_path: str = "state"
    profile_path: str = "profile"
