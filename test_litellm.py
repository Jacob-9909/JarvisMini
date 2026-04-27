import litellm
import os

os.environ["NVIDIA_NIM_API_KEY"] = "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"

try:
    response = litellm.completion(
        model="nvidia_nim/moonshotai/kimi-k2-instruct-0905",
        messages=[{"role": "user", "content": "hi"}],
    )
    print("Success:", response.choices[0].message.content)
except Exception as e:
    print("Error:", e)
