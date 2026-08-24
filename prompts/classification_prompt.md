# Classification Rubric — Hot / Warm / Cold

Applied per turn to the RUNNING state of the call. The LLM proposes; the rubric and
deterministic overrides below decide. Enforced in `src/llm/turn_manager.py`.

## Indirect-signal mapping (from real caller phrasing)

| Caller says | Naive read | Correct read |
|---|---|---|
| "Send me the details" / "WhatsApp karo details" | Mild interest | **Hot-leaning** — buyers ask for details; browsers don't |
| "How soon can you start?" / "Eppudu start chestaru?" | — | **Hot** — urgency question = buying question |
| "What's the price?" + asks about timeline | — | **Hot** if no barrier stated |
| "My brother handles this" / "Anna chustaru" | Rejection | **Warm** — real interest, authority barrier; capture who decides |
| "Budget is not much right now" / "Budget takkuva" | Rejection | **Warm** — need exists, budget barrier; schedule callback |
| "Next month/next year" without rejecting | Rejection | **Warm** — timing barrier |
| "Just looking" / "Not interested" (once, softly) | Cold | **Warm-possible** — probe once more |
| "Not interested" twice / hangs up intent / abuse | — | **Cold** — stop |
| One-word answers, no questions asked, no engagement | — | **Cold** |

## Deterministic overrides (code, not model)

1. Any urgency/timeline QUESTION from caller ⇒ classification floor = warm.
2. Price AND timeline both asked together, no barrier stated ⇒ hot.
3. Explicit "send details/WhatsApp" agreement ⇒ hot (and action=send_whatsapp).
4. Two explicit rejections in the call ⇒ cold, regardless of LLM output.
5. LLM says hot with confidence ≥ 60 ⇒ hot. Warm/cold follow LLM unless an
   override applies.
6. Barrier field wins over classification conflict: stated barrier (budget/
   timing/decision_maker) ⇒ at most warm, never hot, until barrier resolves.

## Running state rules

- Classification is CUMULATIVE: evidence never downgrades without a cause
  (explicit rejection or stated barrier).
- Escalation path: cold → warm → hot as signals accumulate; the agent should
  accelerate toward closure once ≥2 positive signals exist.

## Mid-call action trigger

- WhatsApp "details" message fires the moment running state becomes hot
  (deterministic trigger in code) — not when the model asks permission.
- book_callback fires whenever a time phrase is captured, any classification.
