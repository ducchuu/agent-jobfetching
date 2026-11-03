import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.agent.llm_router import router, GOOGLE_TO_OPENAI_FALLBACK


@pytest.mark.integration
async def test_llm_live_routing():
    response = await router.acompletion(
        model="gemini-4-argon",
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


@pytest.mark.asyncio
@patch("app.agent.llm_router.get_genai_client")
async def test_router_calls_google_genai_primary_flash(mock_get_client):
    mock_client = MagicMock()
    mock_genai_resp = MagicMock()
    mock_genai_resp.text = '{"is_rejected": false, "reason": ""}'
    mock_client.models.generate_content.return_value = mock_genai_resp
    mock_get_client.return_value = mock_client

    response = await router.acompletion(
        model="gemini-3.6-flash",
        messages=[
            {"role": "system", "content": "System instruction"},
            {"role": "user", "content": "User job description"},
        ],
    )

    mock_client.models.generate_content.assert_called_once_with(
        model="gemini-3.6-flash",
        contents="System instruction\n\nUser job description",
    )
    assert response.text == '{"is_rejected": false, "reason": ""}'
    assert response.choices[0].message.content == '{"is_rejected": false, "reason": ""}'


@pytest.mark.asyncio
@patch("app.agent.llm_router.get_genai_client")
async def test_router_calls_google_genai_primary_argon(mock_get_client):
    mock_client = MagicMock()
    mock_genai_resp = MagicMock()
    mock_genai_resp.text = '{"score": 90}'
    mock_client.models.generate_content.return_value = mock_genai_resp
    mock_get_client.return_value = mock_client

    response = await router.acompletion(
        model="gemini-4-argon",
        messages=[
            {"role": "system", "content": "Rubric prompt"},
            {"role": "user", "content": "Job posting"},
        ],
    )

    mock_client.models.generate_content.assert_called_once_with(
        model="gemini-4-argon",
        contents="Rubric prompt\n\nJob posting",
    )
    assert response.text == '{"score": 90}'
    assert response.choices[0].message.content == '{"score": 90}'


@pytest.mark.asyncio
@patch("app.agent.llm_router.litellm_router.acompletion", new_callable=AsyncMock)
@patch("app.agent.llm_router.get_genai_client")
async def test_router_falls_back_to_openai_when_google_fails(mock_get_client, mock_litellm_acompletion):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("Vertex AI quota exceeded")
    mock_get_client.return_value = mock_client

    fallback_resp = MagicMock()
    fallback_resp.choices = [MagicMock(message=MagicMock(content='{"fallback": true}'))]
    mock_litellm_acompletion.return_value = fallback_resp

    # Test gemini-3.6-flash -> gpt-6-luna fallback
    resp_flash = await router.acompletion(
        model="gemini-3.6-flash",
        messages=[{"role": "user", "content": "Test flash"}],
    )
    assert resp_flash.choices[0].message.content == '{"fallback": true}'
    mock_litellm_acompletion.assert_called_with(
        model="gpt-6-luna",
        messages=[{"role": "user", "content": "Test flash"}],
    )

    # Test gemini-4-argon -> gpt-6.1-sol fallback
    resp_argon = await router.acompletion(
        model="gemini-4-argon",
        messages=[{"role": "user", "content": "Test argon"}],
    )
    assert resp_argon.choices[0].message.content == '{"fallback": true}'
    mock_litellm_acompletion.assert_called_with(
        model="gpt-6.1-sol",
        messages=[{"role": "user", "content": "Test argon"}],
    )
    assert GOOGLE_TO_OPENAI_FALLBACK == {
        "gemini-3.6-flash": "gpt-6-luna",
        "gemini-4-argon": "gpt-6.1-sol",
    }
