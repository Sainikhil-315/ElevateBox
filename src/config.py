from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    call_target_number: str = "7093647471"

    openrouter_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_model: str = "google/gemini-2.0-flash-exp:free"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_reasoning_effort: str = "low"
    llm_timeout_first_token: float = 3.0

    deepgram_api_key: str = ""
    deepgram_language: str = "multi"

    deepgram_api_key: str = ""

    google_application_credentials: str = ""
    google_tts_api_key: str = ""
    tts_language_en: str = "en-IN"
    tts_language_hi: str = "hi-IN"
    tts_language_te: str = "te-IN"

    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_api_version: str = "v21.0"
    whatsapp_verify_token: str = ""

    applicant_mobile_number: str = "7093647471"
    applicant_name: str = ""
    resume_url: str = ""
    architecture_image_url: str = ""

    public_webhook_url: str = ""
    port: int = 8000
    database_url: str = "sqlite:///./calls.db"
    enable_media_stream: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
