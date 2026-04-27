import os
import sys

import dotenv
import litellm

dotenv.load_dotenv()

api_key = os.getenv("NVIDIA_NIM_API_KEY")
if not api_key:
    print("❌ NVIDIA_NIM_API_KEY not found in .env")
    sys.exit(1)

print(f"✓ Found API Key (length: {len(api_key)})")

try:
    response = litellm.completion(
        model="nvidia_nim/deepseek-ai/deepseek-v4-pro",
        messages=[{"role": "user", "content": "hi"}],
    )
    print("Success:", response.choices[0].message.content)
except Exception as e:
    print("Error:", e)
