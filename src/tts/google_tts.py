import base64
import time

import audioop
import httpx

from src.config import get_settings

API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

VOICE_BY_LANG = {
    "en": ("en-IN", "en-IN-Neural2-C"),
    "hi": ("hi-IN", "hi-IN-Neural2-A"),
    "te": ("te-IN", "te-IN-Standard-A"),
}

TARGET_RATE = 8000


class TTSError(Exception):
    pass


def synthesize_mulaw(text: str, language: str = "en") -> bytes:
    s = get_settings()
    if not s.google_tts_api_key:
        raise TTSError("GOOGLE_TTS_API_KEY not configured")
    lang_code, voice_name = VOICE_BY_LANG.get(language, VOICE_BY_LANG["en"])
    body = {
        "input": {"text": text},
        "voice": {"languageCode": lang_code, "name": voice_name},
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "sampleRateHertz": 24000,
            "effectsProfileId": ["telephony-class-application"],
            "speakingRate": 1.05,
        },
    }
    t0 = time.perf_counter()
    with httpx.Client(timeout=10.0) as client:
        r = client.post(API_URL, json=body, headers={"x-goog-api-key": s.google_tts_api_key})
    if r.status_code != 200:
        raise TTSError(f"TTS HTTP {r.status_code}: {r.text[:200]}")
    linear24k = base64.b64decode(r.json()["audioContent"])
    pcm_24k = linear24k[44:]
    pcm_8k, _ = audioop.ratecv(pcm_24k, 2, 1, 24000, TARGET_RATE, None)
    mulaw = audioop.lin2ulaw(pcm_8k, 2)
    return mulaw


async def synthesize_mulaw_async(text: str, language: str = "en") -> bytes:
    import asyncio

    t0 = time.perf_counter()
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, synthesize_mulaw, text, language)
    return result


def synthesis_latency(text: str, language: str = "en") -> float:
    t0 = time.perf_counter()
    synthesize_mulaw(text, language)
    return time.perf_counter() - t0
