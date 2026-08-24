from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    call_target_number: str = "7093647471"

    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.0-flash-exp:free"

    deepgram_api_key: str = ""

    google_application_credentials: str = ""
    tts_language_en: str = "en-IN"
    tts_language_hi: str = "hi-IN"
    tts_language_te: str = "te-IN"

    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""

    applicant_mobile_number: str = "7093647471"

    public_webhook_url: str = ""
    port: int = 8000
    database_url: str = "sqlite:///./calls.db"
    enable_media_stream: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
