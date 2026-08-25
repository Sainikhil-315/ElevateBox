from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ==== Telephony (Twilio) ====
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    call_target_number: str = "7093647471"

    # ==== LLM Provider Selection ====
    llm_provider: str = "groq"  # groq | gemini | openai
    llm_reasoning_effort: str = "low"
    llm_timeout_first_token: float = 3.0

    # Groq (fast, free — use for dev/testing)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Gemini (via OpenRouter — fallback option)
    gemini_api_key: str = ""
    gemini_model: str = "google/gemini-2.5-flash-lite:free"
    gemini_base_url: str = "https://openrouter.ai/api/v1"

    # OpenAI (production, once billing is on)
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # ==== Speech-to-text (Deepgram) ====
    deepgram_api_key: str = ""
    deepgram_language: str = "multi"

    # ==== Text-to-speech (Google Cloud) ====
    google_application_credentials: str = ""
    google_tts_api_key: str = ""
    tts_language_en: str = "en-IN"
    tts_language_hi: str = "hi-IN"
    tts_language_te: str = "te-IN"

    # ==== WhatsApp (Meta Cloud API) ====
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_api_version: str = "v21.0"
    whatsapp_verify_token: str = ""

    # ==== Candidate / applicant ====
    applicant_mobile_number: str = "7093647471"
    applicant_name: str = ""
    resume_url: str = ""
    architecture_image_url: str = ""

    # ==== Backend ====
    public_webhook_url: str = ""
    port: int = 8000
    database_url: str = "sqlite:///./calls.db"
    enable_media_stream: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()