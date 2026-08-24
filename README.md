# ElevateBox Voice Agent

AI voice agent that places an outbound sales call for e-commerce website development,
qualifies the lead in Telugu / Hindi / English (including code-switching), classifies
intent as Hot / Warm / Cold from indirect signals, fires a WhatsApp message **mid-call**
on high intent, books callbacks from vague spoken times, and sends a contextual
follow-up WhatsApp with resume + architecture.

Built for the ElevateBox SDE Intern assignment.

## Stack

| Layer | Choice |
|---|---|
| Telephony | Twilio Programmable Voice (`<Connect><Stream>` → WebSocket) |
| STT | Deepgram streaming |
| LLM | OpenRouter (free-tier models; benchmarked before commit) |
| TTS | Google Cloud TTS (`en-IN`, `hi-IN`, `te-IN`) |
| WhatsApp | Meta WhatsApp Business Cloud API |
| Backend | Python 3.11+, FastAPI, asyncio (in-process task queue for mid-call actions) |
| Storage | SQLite via `DATABASE_URL` |
| Hosting | Railway (WebSocket-native, no cold start) |

## Repo structure

```
├── main.py                  # FastAPI entrypoint (/health, outbound trigger)
├── src/
│   ├── config.py            # typed env settings
│   ├── telephony/           # Twilio call placement, media stream handling
│   ├── stt/                 # Deepgram streaming integration
│   ├── llm/                 # OpenRouter client, turn manager
│   ├── tts/                 # Google Cloud TTS
│   ├── whatsapp/            # mid-call + post-call dispatcher (async, retried)
│   ├── scheduler/           # spoken-time parsing → stored timestamps (IST)
│   └── webhooks/            # Twilio status/voice webhooks, Meta webhook
├── prompts/
│   ├── system_prompt.md     # conversation/sales prompt (3 languages)
│   └── classification_prompt.md
├── tests/
└── docs/                    # assignment PDF + project docs
```

## Phone number policy

- `CALL_TARGET_NUMBER` defaults to **7093647471** — the dev/testing number. All build
  and test traffic goes here.
- The final submission target is configured **only** when the full checklist passes.
  Never point the system at it during development.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # fill in credentials
python main.py                # http://localhost:8000/health
```

## Build phases

- [x] Phase 0 — repo scaffold, env contract, health endpoint
- [ ] Phase 1 — Twilio outbound call to dev number + voice/status webhooks live
- [ ] Phase 2 — media stream loop: Twilio → Deepgram STT → OpenRouter → TTS (+ latency benchmark)
- [ ] Phase 3 — system prompt, discovery questions, classification rules + test suite
- [ ] Phase 4 — async mid-call WhatsApp dispatcher + callback scheduling
- [ ] Phase 5 — failure hardening, end-to-end checklist, architecture diagram, handoff note
