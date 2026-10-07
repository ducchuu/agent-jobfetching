import asyncio
from app.agent.llm_router import router
import json

async def test_llm():
    try:
        response = await router.acompletion(
            model="claude-5-5-sonnet",
            max_tokens=2048,
            messages=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": "You are a helpful assistant.",
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                },
                {
                    "role": "user",
                    "content": "Hello, how are you?"
                }
            ]
        )
        print("Response:", response.model_dump_json(indent=2))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test_llm())
