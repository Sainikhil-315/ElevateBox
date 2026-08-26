import asyncio
from src.stt.deepgram_stt import DeepgramStream

async def main():
    dg = DeepgramStream()
    try:
        await dg.start()
        print("Started.")
        async for item in dg.transcripts():
            print(item)
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
