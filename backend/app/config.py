from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://assistant:assistant@localhost:5432/assistant"
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7
    cors_origins: str = "http://localhost:5173"

    # LLM
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "low"  # low cho hội thoại nhanh; tăng lên medium/high nếu cần
    history_turns: int = 10  # số lượt hội thoại trước đó gửi kèm cho LLM

    # Google Calendar (tuỳ chọn). Để trống client_id thì tính năng bị tắt.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Địa chỉ Google gọi lại sau khi đăng nhập; phải khai báo y hệt trong Google Cloud Console.
    # Mặc định đi qua proxy của Vite (frontend) để cookie/địa chỉ khớp với giao diện.
    google_redirect_uri: str = "http://localhost:5173/api/google/callback"
    frontend_url: str = "http://localhost:5173"

    timezone: str = "Asia/Ho_Chi_Minh"
    reminder_poll_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
