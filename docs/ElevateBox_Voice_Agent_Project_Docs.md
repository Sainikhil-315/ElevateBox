# ElevateBox AI Voice Agent — Project Documentation

**Assignment source:** SDE Intern Assignment, ElevateScale Technologies (ElevateBox), Banjara Hills, Hyderabad
**Testing number (use this first):** 7093647471
**Final target number (only call once the flow is solid):** 8688664337
**Stipend:** ₹30,000/month | Deadline: Rolling, no cutoff
**Build approach:** OpenRouter free models (dev) → repo handoff for debugging pass later

> **Important:** Do not point the system at 8688664337 until you've run and validated the full flow against 7093647471. The assignment gives you one real shot — a broken or awkward first call to the founder could hurt more than a delayed submission. Treat 7093647471 as your dev/staging number and 8688664337 as production.

---

## 1. What the PDF Already Tells You

- The call flow: Dial → Speak → Discover → Understand → Classify → Act mid-call → Schedule → Follow up
- 10 hard requirements (calling itself, language handling, discovery questions, classification, mid-call WhatsApp, callback scheduling, contextual follow-up, final WhatsApp package)
- Scoring rubric (100 pts total, 60+ = callback)
- What to send: working prototype + resume + number, to 8688664337
- What NOT to send: decks, proposals, demo videos

This doc covers everything **not** in the PDF — the operational, technical, and account-level groundwork you need before writing code.

---

## 2. Accounts & Access You Need to Set Up

| # | Service | Why | Free tier available? |
|---|---|---|---|
| 1 | **Twilio** | Outbound calling + phone number | Yes, ~$15 trial credit |
| 2 | **Meta WhatsApp Business Cloud API** (via Meta for Developers) | Sending WhatsApp messages mid-call and post-call | Yes, 1,000 free conversations/month |
| 3 | **OpenRouter** | LLM access (your chosen approach) | Yes, several free models available |
| 4 | **Speech-to-text provider** (Soniox, Deepgram, or AssemblyAI) | Live transcription during the call | Yes, most have free trial credits |
| 5 | **Text-to-speech provider** (ElevenLabs, Google Cloud TTS, or OpenAI TTS) | Voice output | Yes, free tiers exist |
| 6 | **Hosting for your webhook backend** (Render, Railway, Fly.io, or ngrok for local dev) | Twilio and WhatsApp need a public HTTPS endpoint to hit | Yes, free tiers work for testing |
| 7 | **GitHub repo** | Version control + what you'll hand me later for debugging | Free |
| 8 | **A calendar/scheduling store** (can just be a simple database table — doesn't need Google Calendar) | Storing booked callback times | N/A — build it yourself |

**Note on Meta WhatsApp API:** you need a Meta Business Account, a verified WhatsApp Business phone number, and app approval for message templates if you want to *initiate* conversations (vs. replying within a 24-hour window). For a live call use case, you're usually sending a **freeform message inside an active session** which is more lenient — but plan a day of buffer for Meta's verification steps since this is the most likely bottleneck in your whole timeline.

---

## 3. What the PDF Doesn't Specify (Decisions You Need to Make)

The PDF is deliberately open-ended ("we don't care about the stack"). You'll need to explicitly decide and document:

1. **Telephony + voice orchestration approach**
   - Fully custom (Twilio Media Streams + your own STT/LLM/TTS pipeline), or
   - A managed voice-agent platform (Vapi, Retell, Bland) that wraps Twilio for you
   - *This is the single biggest architecture decision — it changes your entire build.*

2. **How mid-call actions fire without blocking conversation**
   - You need async function-calling or a parallel process that can send a WhatsApp message while the LLM keeps talking. Document how you're handling this (e.g., background task queue, webhook side-channel).

3. **Language detection & switching strategy**
   - How do you detect Telugu vs Hindi vs English from the caller's first turns, and how do you handle mid-sentence code-switching (which the PDF flags as "normal in this market")?

4. **Classification logic (Hot/Warm/Cold)**
   - This needs to be a documented decision tree or prompt strategy, not just "the LLM decides." Write down your classification prompt/rules so you can defend it (Section 05 of the PDF explicitly scores "engineering judgement — you can defend your choices").

5. **Callback scheduling logic**
   - How do you parse "call me back tomorrow morning" into an actual timestamp? What timezone assumptions are you making? What happens if the time is ambiguous?

6. **Failure handling**
   - What happens if STT drops words, the call disconnects, WhatsApp API fails, or the LLM response takes too long? The PDF explicitly rewards "handles failure" under Engineering Judgement (5 pts) — document your fallback behavior.

---

## 4. Technical Documentation You Should Prepare (Beyond the Code)

These are the artifacts you'll want ready when you send the prototype:

| Deliverable | Required by PDF? | Notes |
|---|---|---|
| Working prototype (callable on demand) | Yes — mandatory | Must dial 8688664337 itself |
| One-page architecture diagram (image/PDF) | Yes — mandatory | Hand-drawn is explicitly fine |
| Short note (<200 words) on what works/doesn't/next steps | Yes — mandatory | Be honest per PDF's own "partial work" note |
| Resume | Yes — mandatory | |
| Your mobile number | Yes — mandatory | |
| Repo link | Optional but recommended | This is what you'll hand to me for debugging |
| `.env.example` file | Not required by them, but good practice | So the code is reproducible without exposing your keys |
| README with setup instructions | Not required by them, but useful for the debugging handoff | Saves me time understanding your repo structure |

---

## 5. Environment Variables You'll Need (Draft `.env` Checklist)

```
# Telephony
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=

# LLM
OPENROUTER_API_KEY=
OPENROUTER_MODEL=            # e.g. a free-tier model you've chosen

# Speech-to-text
STT_API_KEY=

# Text-to-speech
TTS_API_KEY=

# WhatsApp
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=

# Backend
PUBLIC_WEBHOOK_URL=          # your Render/Railway/ngrok URL
DATABASE_URL=                # for storing call context, classification, callback times
```

---

## 6. Suggested Repo Structure (for when you hand it to me)

```
elevatebox-voice-agent/
├── README.md
├── .env.example
├── architecture-diagram.png
├── src/
│   ├── telephony/          # Twilio call handling, media streams
│   ├── stt/                 # speech-to-text integration
│   ├── llm/                 # OpenRouter calls, prompts, classification logic
│   ├── tts/                 # text-to-speech integration
│   ├── whatsapp/             # mid-call + post-call message sending
│   ├── scheduler/           # callback parsing + storage
│   └── webhooks/            # Twilio/WhatsApp inbound webhook handlers
├── prompts/
│   ├── system_prompt.md     # main conversation/sales prompt
│   └── classification_prompt.md
└── tests/
```

Having prompts as separate files (not buried in code) will make it much easier for me to review your classification/sales logic quality when you hand this off.

---

## 7. Testing Checklist Before You Call Them

- [ ] All testing done against 7093647471 first — do not dial 8688664337 until every box below is checked
- [ ] System dials out on its own (no manual trigger from a human)
- [ ] Handles at least one full conversation in each language (Telugu, Hindi, English)
- [ ] Survives interruption (caller talks over the bot)
- [ ] Correctly classifies at least 3 test scenarios (clearly hot, clearly warm, clearly cold — using indirect phrasing, per PDF's own examples)
- [ ] WhatsApp fires **during** a live call, not after hangup
- [ ] A spoken vague time ("tomorrow morning") gets converted to an actual scheduled callback
- [ ] Final WhatsApp message contains all 4 required elements: call context in natural language, your number, resume, and architecture image
- [ ] You've tested a call that goes badly (silence, disconnection) and confirmed it doesn't crash

---

## 8. Suggested Timeline (Adjusted for OpenRouter Free Models)

Free-tier LLM models may have higher latency or rate limits than paid Claude API — worth testing early since the PDF explicitly flags **latency** as a top failure mode ("if the reply takes three seconds, the conversation is dead").

| Day | Focus |
|---|---|
| 1 | Twilio account + number, basic outbound call working, hello-world webhook live |
| 2 | STT + OpenRouter LLM + TTS wired into the call loop, test round-trip latency |
| 3 | Discovery questions, classification logic, prompt tuning across all 3 languages |
| 4 | WhatsApp mid-call trigger + callback scheduling logic |
| 5 | End-to-end testing, failure handling, architecture diagram, README, package for handoff |

If OpenRouter free models prove too slow for real-time conversation, that's worth discovering on Day 2 — not Day 4 — so you have runway to switch.

---

*When you're ready to hand off the repo, send it over and I'll go through it for gaps — particularly around mid-call action firing, classification robustness, and failure handling, since those are the areas the scorecard weights heaviest and where free-tier models are most likely to need patching.*