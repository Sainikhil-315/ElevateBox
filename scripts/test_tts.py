import base64
import os
import time
import wave
from pathlib import Path

import httpx

API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
VOICES_URL = "https://texttospeech.googleapis.com/v1/voices"

CASES = [
    ("en-IN", "en-IN-Neural2-C", "Hello! I am calling about building an e-commerce website for your shop."),
    ("hi-IN", "hi-IN-Neural2-A", "नमस्ते! मैं आपके व्यापार के लिए ई-कॉमर्स वेबसाइट बनाने के बारे में बात करनी थी।"),
    ("te-IN", "te-IN-Standard-A", "నమస్కారం! మీ వ్యాపారం కోసం ఈ-కామర్స్ వెబ్‌సైట్ గురించి మాట్లాడాలనుకుంటున్నాను."),
]


def get_api_key():
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if key:
        return key
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GOOGLE_TTS_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def save_mp3(path, audio_b64):
    Path(path).write_bytes(base64.b64decode(audio_b64))


def save_wav(path, audio_b64, sample_rate):
    pcm = base64.b64decode(audio_b64)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm)


def main():
    key = get_api_key()
    if not key:
        print("ERROR: GOOGLE_TTS_API_KEY not set in .env")
        return 1

    out_dir = Path("C:/Users/saini/AppData/Local/Temp/opencode/tts_smoke")
    out_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=30) as client:
        for lang, voice, text in CASES:
            body = {
                "input": {"text": text},
                "voice": {"languageCode": lang, "name": voice},
                "audioConfig": {
                    "audioEncoding": "LINEAR16",
                    "sampleRateHertz": 24000,
                    "effectsProfileId": ["telephony-class-application"],
                },
            }
            t0 = time.perf_counter()
            r = client.post(API_URL, json=body, headers={"x-goog-api-key": key})
            elapsed = time.perf_counter() - t0
            if r.status_code != 200:
                print(f"FAIL {lang}: HTTP {r.status_code}: {r.text[:300]}")
                continue
            data = r.json()
            b64 = data["audioContent"]
            wav_path = out_dir / f"tts_{lang}.wav"
            save_wav(wav_path, b64, 24000)
            print(f"OK   {lang} voice={voice} latency={elapsed:.2f}s -> {wav_path}")

    print(f"\nListen to the files in: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
