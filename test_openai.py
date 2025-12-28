#!/usr/bin/env python
"""Simple script to test OpenAI API key."""

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

print(f"API Key loaded: {'Yes' if api_key else 'No'}")
if api_key:
    # Show first and last 4 characters for verification
    masked = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
    print(f"API Key (masked): {masked}")
    print(f"API Key length: {len(api_key)}")

# Test the API
try:
    from openai import OpenAI
    
    client = OpenAI(api_key=api_key)
    
    print("\nTesting API connection...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say 'Hello, API works!'"}],
        max_tokens=20
    )
    
    print(f"✅ API Response: {response.choices[0].message.content}")
    
except Exception as e:
    print(f"❌ API Error: {e}")
