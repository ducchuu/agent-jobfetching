import pytest
from app.agent.llm_router import router

@pytest.mark.integration
async def test_llm_live_routing():
    response = await router.acompletion(
        model="claude-5-5-sonnet",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": "Respond with the single word: OK"
            }
        ]
    )
    assert response is not None
    assert len(response.choices) > 0
    content = response.choices[0].message.content
    assert content is not None
    assert len(content.strip()) > 0
