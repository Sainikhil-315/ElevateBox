# Live Demo Test Scripts — 3 Intent Scenarios

Play these on the phone when Priya calls 7093647471. Each targets a different
intent. After each call, check the server logs for `LEAD-CHANGE` and `INTENT` lines
and confirm the final classification matches the expected one.

---

## Script 1 — HOT (expected: hot, WhatsApp should fire mid-call)

You run a mobile accessories shop and you NEED a website soon. Ask price early,
ask timeline, agree to WhatsApp.

- "Haan hello?"
- "Haan bhai, tell me"
- "Mobile accessories shop anna, Guntur lo. Charger covers earphones anni vuntayi"
- "Around 300-400 items vuntayi shop lo"
- "Website enduku kavali ante, big days lo sales ekkuva avvali, Diwali ki ready ga vundali"
- "Enta cost avtundi roughly?"
- "OK ok. Inka eppudu ready cheyyagalaru?"
- "Payment options kuda vundaa? UPI and cards?"
- "Haan haan super. WhatsApp cheseyyandi details, chuskuntam"
- "Sare anna, thank you"

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
indifferent like someone busy.

- "Hello?"
- "Kaun cheppu... evaru?"
- "Website aa... naku enduku le"
- "Em panchavvadu online lo... naku antha scene ledu"
- "Konchem busy ga vunna, inko call cheyyi time ki"
- "Haan sare sare, bye"

Expected log trail: deflection/negative signals -> stays COLD -> no WhatsApp
action -> polite short close from bot
