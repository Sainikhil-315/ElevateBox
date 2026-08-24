# Classification Prompt — Hot / Warm / Cold (DRAFT: filled in Phase 3)

Purpose: per-turn intent classification with strict JSON output + deterministic
override rules layered on top in code.

Planned contents:
- Output schema: {signals[], classification, confidence, barrier}
- Indirect-signal rubric (from assignment examples):
  - "send me the details"        -> hot-leaning
  - "how soon can you start?"    -> hot (urgency)
  - "my brother handles this"    -> warm (authority barrier)
  - "budget is not much now"     -> warm (budget barrier)
- Deterministic overrides (enforced in src/llm, not by the model):
  - urgency/timeline question => floor of Warm
  - price AND timeline asked together, no stated barrier => Hot
  - two explicit rejections => Cold
- Running classification: cumulative evidence across turns, not single-turn verdict
