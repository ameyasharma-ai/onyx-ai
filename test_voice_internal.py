import asyncio
import httpx
import hashlib
import sys

async def main():
    async with httpx.AsyncClient() as client:
        print("Request 1")
        res1 = await client.post(
            "http://qwen3_tts:8000/audio/speech", 
            json={"text": "Hello world this is a test.", "voice": "699aac14-22d1-4269-8cd3-dd4984351976"},
            timeout=None
        )
        print("Status 1:", res1.status_code)
        hash1 = hashlib.md5(res1.content).hexdigest()
        print("Hash 1:", hash1)
        
        print("Request 2")
        res2 = await client.post(
            "http://qwen3_tts:8000/audio/speech", 
            json={"text": "Hello world this is a test.", "voice": "699aac14-22d1-4269-8cd3-dd4984351976"},
            timeout=None
        )
        print("Status 2:", res2.status_code)
        hash2 = hashlib.md5(res2.content).hexdigest()
        print("Hash 2:", hash2)
        
        if hash1 == hash2:
            print("SUCCESS! Output is identical.")
        else:
            print("FAILED! Output is different.")

if __name__ == "__main__":
    asyncio.run(main())
