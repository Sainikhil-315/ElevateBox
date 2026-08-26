# Live Demo Test Scripts — 3 Intent Scenarios

Play these on the phone when Priya calls 7093647471. Each targets a different
intent. After each call, check the server logs for `LEAD-CHANGE` and `INTENT` lines
and confirm the final classification matches the expected one.

Languages: Hindi + English (incl. Hinglish) — Deepgram nova-3 covers these two.

---

## Script 1 — HOT (expected: hot, WhatsApp should fire mid-call)

You run a mobile accessories shop and you NEED a website soon. Ask price early,
ask timeline, agree to WhatsApp. Mix Hindi-English naturally.

- "Haan hello?"
- "Haan bhai, boliye"
- "Mobile accessories ki dukaan hai meri, Guntur mein. Charger, covers, earphones sab"
- "Around 300-400 items hain dukaan pe"
- "Website kyun chahiye... Diwali pe sales badhani hai, us se pehle ready chahiye"
- "Kitne ka padega roughly?"
- "OK ok. Aur kab tak ready kar paoge?"
- "Payment options bhi honge na? UPI, cards?"
- "Haan haan badhiya. WhatsApp kar do details, dekh leta hoon"
- "Theek hai bhai, thank you"

Expected log trail: signals with budget + timeline/urgency positive -> LEAD-CHANGE
-> HOT -> action={'type': 'send_whatsapp'}

---

## Script 2 — WARM (expected: warm with barrier, callback should get booked)

Interested, but money is tight right now and your brother takes final decisions.
Don't say "I am warm" — be indirect like a real person. Also name a vague callback
time.

- "Hello... kaun ji?"
- "Haan bolo"
- "Arre haan website... dekhenge hum bhi. Dukaan hai meri, kirana ki"
- "Haan online bechna hai toh sahi hai, sab log kar rahe hain aajkal"
- "Budget ka... woh thoda problem hai. Abhi itna paisa nahi hai kharch karne ko"
- "Aur ghar mein saare faisla bhaiya hi lete hain, main akele kuch nahi bol sakta"
- "Nahi nahi, interest toh hai. Bas abhi season kharab hai"
- "Aise karo, kal subah call kar lena, shaam ko main bhaiya se baat kar lunga"
- "Theek hai theek hai, dekhte hain"

Expected log trail: barrier=budget and/or decision_maker -> capped at WARM ->
callback_phrase captured -> resolved timestamp in logs

---

## Script 3 — COLD (expected: cold, polite quick close)

Just picked up randomly, zero interest, minimal answers. Don't be rude, just be
indifferent like someone busy. Full English this time — tests the English path.

- "Hello?"
- "Who is this... what's this about?"
- "A website? Nah, I don't think I need one"
- "I don't really sell anything online... it's a small shop"
- "Look, I'm a bit busy right now, call me some other time"
- "Yeah yeah, fine, bye"

Expected log trail: deflection/negative signals -> stays COLD -> no WhatsApp
action -> polite short close from bot
