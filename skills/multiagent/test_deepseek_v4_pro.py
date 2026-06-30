#!/usr/bin/env python3
"""
Test DeepSeek V4 Pro API directly
"""
import asyncio
import json
import os
import sys
import httpx

# Add current directory to Python path
sys.path.insert(0, '.')

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/anthropic/v1/messages"
DEEPSEEK_MODEL = "deepseek-v4-pro"

async def test_deepseek_v4_pro():
    if not DEEPSEEK_API_KEY:
        print("ERROR: DEEPSEEK_API_KEY not set")
        return

    payload = {
        "model": DEEPSEEK_MODEL,
        "max_tokens": 4096,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant."
            },
            {
                "role": "user",
                "content": "What is Python?"
            }
        ]
    }

    print("Testing DeepSeek V4 Pro API...")
    print(f"URL: {DEEPSEEK_API_URL}")
    print(f"Model: {DEEPSEEK_MODEL}")
    print(f"Key: {DEEPSEEK_API_KEY[:10]}...")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            resp = await client.post(
                DEEPSEEK_API_URL,
                json=payload,
                headers={
                    "x-api-key": DEEPSEEK_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                }
            )
            print(f"Status Code: {resp.status_code}")
            print(f"Response Headers: {resp.headers}")

            if resp.status_code == 200:
                data = resp.json()
                print("SUCCESS!")
                print("Response:", json.dumps(data, indent=2))
            else:
                print("ERROR Response:")
                print(resp.text)

    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_deepseek_v4_pro())