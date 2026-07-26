import os

import pytest

from dermiq.api.schemas import ChatResponse

pytestmark = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"),
    reason="requires live Snowflake credentials",
)

TENANT_HEADERS = {"X-Tenant-ID": "del_mar"}


def test_chat_missing_header_400(client):
    assert client.post("/api/v1/chat", json={"question": "hello"}).status_code == 400


def test_chat_blank_question_422(client):
    r = client.post("/api/v1/chat", json={"question": ""}, headers=TENANT_HEADERS)
    assert r.status_code == 422


def test_chat_whitespace_question_422(client):
    r = client.post("/api/v1/chat", json={"question": "   "}, headers=TENANT_HEADERS)
    assert r.status_code == 422


def test_chat_200_grounded_answer(client):
    r = client.post(
        "/api/v1/chat",
        json={"question": "Which patient segments are highest value?"},
        headers=TENANT_HEADERS,
    )
    assert r.status_code == 200
    body = ChatResponse.model_validate(r.json())
    assert body.answer.strip()
    assert len(body.sources) > 0
