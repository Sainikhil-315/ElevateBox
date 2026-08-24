# ElevateBox Voice Agent — Build Plan & Architecture Decisions

> Working plan for the full build. Status updated as phases complete.
> **Phone policy:** all dev/test traffic targets **7093647471** only. The founder's
> number is configured exclusively at final submission after every checklist item passes.

---

## 1. Scoring priorities (from assignment PDF Section 05)

| Area | Points | Priority |
|---|---|---|
| Calls & holds a conversation | 25 | P0 — depends on latency & turn-taking |
| Intent classification | 15 | P0 |
| Mid-call WhatsApp action | 15 | P0 |
| Language handling (Te/Hi/En + code-switching) | 10 | P1 |
| Discovery quality | 10 | P1 |
| Callback scheduling from speech | 10 | P1 |
| Follow-up & WhatsApp quality | 10 | P1 |
| Engineering judgement | 5 | P2 — cheap points via failure matrix |

Top-3 = 55 pts; threshold for callback is 60.

---

## 2. Stack decisions

| Layer | Choice | Notes / risk |
|---|---|---|
| Telephony | Twilio `<Connect><Stream>` → our WebSocket | Full control of audio path |
| STT | Deepgram streaming | endpointing ~200ms; Telugu quality to verify |
| LLM | OpenRouter free tier | Final model chosen by `scripts/benchmark_llm.py` results (TTFT, first-sentence latency, JSON compliance). Default candidate: `google/gemini-2.0-flash-exp:free` |
| TTS | Google Cloud TTS (`en-IN` / `hi-IN` / `te-IN`) | Only solid free Telugu voice option |
| WhatsApp | Meta Cloud API | Business verification = biggest schedule risk, start early |
| Backend | FastAPI + asyncio, in-process task queue | WebSocket-native hosting needed |
| Hosting | Railway | Render free tier cold-starts kill webhooks |
| Storage | SQLite (`calls`, `turn_events`, scheduler, `failed_actions`) | |

### Latency budget per conversational turn

| Stage | Target |
|---|---|
| Twilio transport | ~100–200ms |
| Deepgram endpointing → final transcript | ~200–400ms |
| LLM TTFT (free pool) | 0.3–0.8s flash-class; 1–3s+ dense — benchmark decides |
| First sentence streamed to TTS | ~300–500ms |
| TTS synth of sentence 1 | ~200–400ms |
| **Total** | **~1.2s best / 1.5–2.5s typical / 3s+ unacceptable** |

Mitigations: token streaming into sentence-chunked TTS, speculative LLM start on
interim transcripts, rolling-summary context instead of unbounded transcript,
3s first-token timeout with scripted fallback line.

Free-model weak points tracked explicitly: rate limits (~20 req/min on some models),
degraded strict-JSON adherence, weak Telugu. Benchmark harness:
`python scripts/benchmark_llm.py --runs 5`.

---

## 3. Build order & status

| Phase | Scope | Status |
|---|---|---|
| 0 | Repo scaffold, env contract, health endpoint, README | ✅ Done (`1b127d8`) |
| 0.5 | OpenRouter benchmark harness (`scripts/benchmark_llm.py`) | ✅ Done (`11d9444`) — awaiting API key to run |
| 1 | Twilio outbound dialer, voice/status webhooks + signature validation, media WS stub, SQLite call tracking | ✅ Code done (`599c799`) — live test pending Twilio creds |
| 2 | Media loop: Twilio WS → Deepgram STT → OpenRouter → TTS → back; barge-in (clear-buffer + echo suppression); latency measurement | ⬜ Next |
| 3 | System prompt (3 languages), discovery questions, classification prompt + deterministic overrides, dialogue test suite | ⬜ |
| 4 | Async mid-call WhatsApp dispatcher + callback scheduling (IST resolver) | ⬜ |
| 5 | Failure hardening, end-to-end checklist vs dev number, architecture diagram, final WhatsApp payload, handoff note | ⬜ |

Each completed phase is committed and pushed to GitHub.

---

## 4. Mid-call action architecture (the hard part)

```
Twilio PSTN ──audio── <Connect><Stream> ══WS══> FastAPI /media
                                                  │
        ┌─────────────────────────────────────────┤
        ▼                 ▼                       ▼
  Deepgram STT      Turn Manager            TTS (sentence-chunked)
  final transcripts dialog state                 │
        │                 │                       ▼
        └─ transcript ─►  LLM ──audio frames──► back into WS
                          │
                     classification crosses HOT?
                          │
                          ▼
          asyncio.create_task(...)   ← fire-and-forget; WS loop NEVER awaits
                          │
                          ▼
          Background dispatcher: idempotency guard (call_sid, action),
          retry ×3 exp backoff (2/8/32s), dead-letter row on total failure
                          │
                          ▼
          Meta Graph API → caller's phone while call is still live
```

Key mechanics:
- Dispatch triggered **deterministically** by the rule engine crossing HOT — never
  dependent on the LLM remembering to emit a tool call. The LLM only supplies the
  spoken narration line ("sending the details right now"); canned bridge line if omitted.
- Idempotency keyed `(call_sid, action_type)` prevents double sends.
- Agent verbally mentions the send mid-call — audible proof of mid-call firing.

---

## 5. Classification design (defensible, hybrid)

Per-turn strict JSON from LLM:

```json
{
  "signals": [{"quote": "...", "type": "budget|timeline|urgency|authority|need|deflection", "polarity": "positive|negative|neutral"}],
  "classification": "hot|warm|cold",
  "confidence": 0-100,
  "barrier": null|"budget"|"timing"|"decision_maker"|"other"
}
```

Indirect-signal rubric (from PDF Section 03 examples):

| Caller says | Correct read |
|---|---|
| "Send me the details" | Hot-leaning |
| "How soon can you start?" | Hot (urgency) |
| "My brother handles this" | Warm (authority barrier) |
| "Budget is not much right now" | Warm (budget barrier) |

Deterministic overrides enforced in code, not by the model:
- urgency/timeline question ⇒ floor Warm
- price AND timeline asked together, no barrier stated ⇒ Hot
- two explicit rejections ⇒ Cold

Running cumulative state per call, re-evaluated every turn. Anti-hangup measures:
at ≥2 positive signals agent forces closure ("Shall I WhatsApp you the details now?");
post-drop re-classification over the full transcript fires follow-up within seconds
(honest limitation: technically post-call).

Override thresholds are hypotheses until Phase 3's scripted-dialogue test suite
(includes the exact PDF phrases) passes; they are tuned there, documented in
`prompts/classification_prompt.md`.

---

## 6. Callback scheduling rules (Asia/Kolkata throughout)

Pipeline: speech → LLM extracts raw time phrase → deterministic resolver stores ISO-8601
timestamp. The LLM never invents dates.

Defaults: morning→10:30, afternoon→14:00, evening/tonight→19:00, bare weekday→next
occurrence 11:00. Explicit times PM-biased unless "morning/am" present.
Past-time rule: resolved ≤ now+30min ⇒ roll to tomorrow same daypart; impossible
explicit "today" ⇒ in-call clarification.
Ambiguity protocol: low confidence ⇒ confirm-question replaces the standard echo turn
("Kal subah 10:30 ke around?") — zero extra turns vs baseline. Resolved time always
echoed aloud before booking. Original phrase + resolved timestamp stored for audit.

---

## 7. Failure handling matrix

| Failure | Behavior |
|---|---|
| Call drops | `statusCallback` (completed/busy/no-answer/failed/canceled) → persist partial transcript + last classification; contextual follow-up still sent if ≥1 signal captured; logged |
| STT mishears | Deepgram confidence < 0.6 ⇒ ask to repeat; numbers/budget echoed back before storing |
| WhatsApp fails mid-call | async retries ×3 backoff; never blocks speech; on total failure merges into post-call message + `failed_actions` row |
| LLM timeout >3s | natural filler line, one retry with trimmed context, then scripted next discovery question — conversation never dies; event logged per model |
| Silence from caller | 2 nudge prompts, then polite close + Cold + follow-up sent |
| Malformed LLM JSON | fence-stripping/regex extraction; else scripted safety response by dialog state |

Follow-up tiers (never generic): full context quotes specifics → 1-signal calls quote
that one concrete thing → zero-content drops get short intro carrying all four mandatory
elements (context section honestly reduced).

---

## 8. End-to-end checklist before pointing at any new number

- [ ] Full outbound call works against 7093647471
- [ ] One complete conversation each in Telugu, Hindi, English (+ code-switch)
- [ ] Survives interruption (barge-in stops bot audio)
- [ ] 3 scripted scenarios classify correctly using indirect phrasing
- [ ] WhatsApp lands **during** a live call
- [ ] Vague spoken time becomes a stored IST timestamp + audible confirmation
- [ ] Final WhatsApp carries: call-context in natural language, applicant number, resume, architecture image
- [ ] Dropped-call and silence scenarios don't crash; graceful messages sent
