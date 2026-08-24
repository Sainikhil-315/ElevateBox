import asyncio
import time

from src.llm.client import chat_once
from src.llm.turn_manager import TurnManager


async def main():
    tm = TurnManager("smoke-test")
    turns = [
        "Hello, who is this?",
        "Naa duukaan lo clothes vuntayi. Website kavali but budget takkuva, entha avtundi?",
        "How soon can you start? Send me the details on WhatsApp.",
    ]
    for t in turns:
        t0 = time.perf_counter()
        result = await tm.handle_transcript(t)
        dt = time.perf_counter() - t0
        print(f"[{dt:.2f}s] cls={result.classification} lang={result.language} fallback={result.used_fallback}")
        print(f"  reply: {result.reply[:150]}")
        print(f"  action: {result.action}")
        print()


asyncio.run(main())
