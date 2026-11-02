import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from backend.config import get_settings
from backend.services.learning_tutor import explain_answer

QUESTION = {
    "id": "q1",
    "question": "Why use React keys?",
    "options": [{"id": "a", "text": "Styling"}, {"id": "b", "text": "Identity"}],
    "answer": {"correctOptionId": "b", "explanation": "Keys preserve identity."},
}


def test_groq_receives_authoritative_question_and_selected_answer(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_key", "test-only-key")
    real_client = httpx.AsyncClient

    def handle(request):
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-only-key"
        payload = json.loads(request.content)
        assert payload["model"] == "openai/gpt-oss-20b"
        context = json.loads(payload["messages"][1]["content"])
        assert context["selectedOptionId"] == "a"
        assert context["question"]["answer"]["correctOptionId"] == "b"
        assert payload["messages"][-1]["content"] == "Give me an example."
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Keys identify items."}}]}
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw),
    )
    result = asyncio.run(explain_answer(QUESTION, "a", "Give me an example.", []))
    assert result == "Keys identify items."


def test_tutor_missing_key_is_an_explicit_configuration_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    with pytest.raises(HTTPException) as error:
        asyncio.run(explain_answer(QUESTION, "a", "Why?", []))
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "AI_NOT_CONFIGURED"


@pytest.mark.parametrize("status", [401, 429, 500])
def test_provider_errors_do_not_expose_provider_body_or_key(monkeypatch, status):
    monkeypatch.setattr(get_settings(), "groq_api_key", "test-only-key")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, text="secret-provider-body")
            ),
            **kw,
        ),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(explain_answer(QUESTION, "a", "Why?", []))
    assert "secret-provider-body" not in str(error.value.detail)
    assert "test-only-key" not in str(error.value.detail)
    assert error.value.status_code == (429 if status == 429 else 503)


def test_unavailable_model_returns_actionable_configuration_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "test-only-key")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    404,
                    json={
                        "error": {
                            "code": "model_not_found",
                            "message": "private-provider-message",
                        }
                    },
                )
            ),
            **kw,
        ),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(explain_answer(QUESTION, "a", "Why?", []))
    assert error.value.detail["code"] == "AI_MODEL_UNAVAILABLE"
    assert "GROQ_MODEL" in error.value.detail["message"]
    assert "private-provider-message" not in str(error.value.detail)
