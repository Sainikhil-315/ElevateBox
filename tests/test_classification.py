from src.llm.turn_manager import RunningState, _normalize


def state():
    return RunningState()


def sig(t="need", p="positive", q=""):
    return {"quote": q, "type": t, "polarity": p}


def test_hot_from_details_request():
    s = state()
    parsed = _normalize({
        "classification": "hot", "confidence": 70, "barrier": None, "language": "en",
        "signals": [sig("need", "positive", "send me the details")],
    })
    assert s.apply(parsed) == "hot"


def test_authority_barrier_caps_warm():
    s = state()
    parsed = _normalize({
        "classification": "hot", "confidence": 80, "barrier": "decision_maker", "language": "en",
        "signals": [sig("authority", "negative", "my brother handles this")],
    })
    assert s.apply(parsed) == "warm"
    assert s.barrier == "decision_maker"


def test_budget_barrier_caps_warm():
    s = state()
    parsed = _normalize({
        "classification": "hot", "confidence": 75, "barrier": "budget", "language": "en",
        "signals": [sig("budget", "negative", "budget is not much right now")],
    })
    assert s.apply(parsed) == "warm"


def test_timeline_question_floor_warm():
    s = state()
    parsed = _normalize({
        "classification": "warm", "confidence": 60, "barrier": None, "language": "en",
        "signals": [sig("timeline", "positive", "how soon can you start?")],
    })
    assert s.apply(parsed) == "warm"


def test_price_and_timeline_hot():
    s = state()
    parsed = _normalize({
        "classification": "warm", "confidence": 60, "barrier": None, "language": "en",
        "signals": [sig("budget", "positive", "what is the price?"), sig("timeline", "positive", "how soon?")],
    })
    assert s.apply(parsed) == "hot"


def test_two_rejections_cold():
    s = state()
    first = _normalize({
        "classification": "warm", "confidence": 50, "barrier": None, "language": "en",
        "signals": [sig("deflection", "negative", "not interested")],
    })
    s.apply(first)
    assert s.classification != "cold"
    s.apply(first)
    assert s.classification == "cold"


def test_classification_never_downgrades_without_cause():
    s = state()
    hot = _normalize({
        "classification": "hot", "confidence": 80, "barrier": None, "language": "en",
        "signals": [sig("need", "positive", "I want a website")],
    })
    assert s.apply(hot) == "hot"
    weak = _normalize({
        "classification": "warm", "confidence": 40, "barrier": None, "language": "en",
        "signals": [],
    })
    s.apply(weak)
    assert s.classification == "hot"


def test_language_tracked():
    s = state()
    parsed = _normalize({
        "classification": "warm", "confidence": 60, "barrier": None, "language": "te",
        "signals": [sig()],
    })
    s.apply(parsed)
    assert s.language == "te"

def test_no_downgrade_on_noise_turn_with_barrier():
    s = state()
    hot = _normalize({
        "classification": "hot", "confidence": 85, "barrier": None, "language": "hi",
        "signals": [sig("urgency", "positive", "Diwali tak ready chahiye")],
    })
    assert s.apply(hot) == "hot"
    noise = _normalize({
        "classification": "warm", "confidence": 70, "barrier": "budget", "language": "hi",
        "signals": [sig("budget", "neutral", "budget")],
    })
    s.apply(noise)
    assert s.classification == "hot"
    assert s.barrier is None


def test_barrier_accepted_only_with_negative_signal_or_high_confidence():
    s = state()
    weak = _normalize({
        "classification": "warm", "confidence": 60, "barrier": "budget", "language": "en",
        "signals": [sig("budget", "neutral", "budget")],
    })
    s.apply(weak)
    assert s.barrier is None
    strong = _normalize({
        "classification": "warm", "confidence": 80, "barrier": "budget", "language": "en",
        "signals": [sig("budget", "neutral", "what is your budget range")],
    })
    s.apply(strong)
    assert s.barrier == "budget"
    assert s.classification == "warm"
