# ============================================================
# Tests for Fazle Brain — Content Safety Module
# Verifies fail-closed behavior for child accounts when the
# OpenAI Moderation API is unavailable.
#
# Run:  pytest tests/test_safety_fail_closed.py -v
# ============================================================
import pytest
import httpx
import sys
import os

# Allow importing safety module from brain directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fazle-system", "brain"))

from safety import (
    check_content,
    CHILD_BLOCKED_RESPONSE,
    CHILD_THRESHOLDS,
    DEFAULT_THRESHOLDS,
)


FAKE_API_KEY = "sk-test-key-not-real"


# ── Fail-closed tests (child accounts) ─────────────────────

@pytest.mark.asyncio
async def test_child_daughter_blocked_on_api_timeout(monkeypatch):
    """When moderation API times out, daughter accounts must be BLOCKED."""

    async def mock_post(self, *args, **kwargs):
        raise httpx.ConnectTimeout("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await check_content(
        text="Hello there",
        openai_api_key=FAKE_API_KEY,
        relationship="daughter",
    )

    assert result["safe"] is False
    assert result["reason"] == "moderation_unavailable"
    assert result["blocked_reply"] == CHILD_BLOCKED_RESPONSE


@pytest.mark.asyncio
async def test_child_son_blocked_on_api_timeout(monkeypatch):
    """When moderation API times out, son accounts must be BLOCKED."""

    async def mock_post(self, *args, **kwargs):
        raise httpx.ConnectTimeout("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await check_content(
        text="Hello there",
        openai_api_key=FAKE_API_KEY,
        relationship="son",
    )

    assert result["safe"] is False
    assert result["reason"] == "moderation_unavailable"
    assert result["blocked_reply"] == CHILD_BLOCKED_RESPONSE


@pytest.mark.asyncio
async def test_child_generic_blocked_on_api_error(monkeypatch):
    """When moderation API returns a server error, 'child' accounts
    must be BLOCKED (fail closed)."""

    async def mock_post(self, *args, **kwargs):
        raise httpx.HTTPStatusError(
            "Internal Server Error",
            request=httpx.Request("POST", "https://api.openai.com/v1/moderations"),
            response=httpx.Response(500),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await check_content(
        text="Some text",
        openai_api_key=FAKE_API_KEY,
        relationship="child",
    )

    assert result["safe"] is False
    assert result["reason"] == "moderation_unavailable"
    assert result["blocked_reply"] == CHILD_BLOCKED_RESPONSE


@pytest.mark.asyncio
async def test_child_blocked_on_network_error(monkeypatch):
    """Network-level failure must also block child accounts."""

    async def mock_post(self, *args, **kwargs):
        raise httpx.ConnectError("DNS resolution failed")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await check_content(
        text="Testing content",
        openai_api_key=FAKE_API_KEY,
        relationship="daughter",
    )

    assert result["safe"] is False
    assert result["reason"] == "moderation_unavailable"


# ── Fail-open tests (adult accounts) ───────────────────────

@pytest.mark.asyncio
async def test_adult_allowed_on_api_timeout(monkeypatch):
    """When moderation API times out, adult (wife) accounts should
    fail OPEN — content is allowed through."""

    async def mock_post(self, *args, **kwargs):
        raise httpx.ConnectTimeout("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await check_content(
        text="Hello there",
        openai_api_key=FAKE_API_KEY,
        relationship="wife",
    )

    assert result["safe"] is True
    assert result.get("reason") == "moderation_unavailable"


@pytest.mark.asyncio
async def test_adult_self_allowed_on_api_error(monkeypatch):
    """When moderation API fails, 'self' (admin) accounts should
    fail OPEN."""

    async def mock_post(self, *args, **kwargs):
        raise httpx.HTTPStatusError(
            "Bad Gateway",
            request=httpx.Request("POST", "https://api.openai.com/v1/moderations"),
            response=httpx.Response(502),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await check_content(
        text="Some message",
        openai_api_key=FAKE_API_KEY,
        relationship="self",
    )

    assert result["safe"] is True


@pytest.mark.asyncio
async def test_adult_no_relationship_allowed_on_api_error(monkeypatch):
    """When no relationship is specified, fail OPEN on API errors."""

    async def mock_post(self, *args, **kwargs):
        raise httpx.ConnectTimeout("Timeout")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await check_content(
        text="Content",
        openai_api_key=FAKE_API_KEY,
        relationship=None,
    )

    assert result["safe"] is True


# ── Normal operation tests ──────────────────────────────────

@pytest.mark.asyncio
async def test_safe_content_passes(monkeypatch):
    """Normal safe content should pass moderation."""

    async def mock_post(self, *args, **kwargs):
        mock_resp = httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": False,
                        "category_scores": {
                            "sexual": 0.001,
                            "hate": 0.001,
                            "harassment": 0.001,
                            "self-harm": 0.001,
                            "sexual/minors": 0.0001,
                            "hate/threatening": 0.001,
                            "violence/graphic": 0.001,
                            "violence": 0.001,
                            "harassment/threatening": 0.001,
                            "self-harm/intent": 0.001,
                            "self-harm/instructions": 0.001,
                        },
                    }
                ]
            },
            request=httpx.Request("POST", "https://api.openai.com/v1/moderations"),
        )
        return mock_resp

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await check_content(
        text="How is the weather today?",
        openai_api_key=FAKE_API_KEY,
        relationship="daughter",
    )

    assert result["safe"] is True


@pytest.mark.asyncio
async def test_unsafe_content_blocked_for_child(monkeypatch):
    """Content exceeding child thresholds must be blocked."""

    async def mock_post(self, *args, **kwargs):
        mock_resp = httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": True,
                        "category_scores": {
                            "sexual": 0.8,
                            "hate": 0.001,
                            "harassment": 0.001,
                            "self-harm": 0.001,
                            "sexual/minors": 0.0001,
                            "hate/threatening": 0.001,
                            "violence/graphic": 0.001,
                            "violence": 0.001,
                            "harassment/threatening": 0.001,
                            "self-harm/intent": 0.001,
                            "self-harm/instructions": 0.001,
                        },
                    }
                ]
            },
            request=httpx.Request("POST", "https://api.openai.com/v1/moderations"),
        )
        return mock_resp

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await check_content(
        text="Inappropriate content",
        openai_api_key=FAKE_API_KEY,
        relationship="daughter",
    )

    assert result["safe"] is False
    assert result["reason"] == "sexual"
    assert result["blocked_reply"] == CHILD_BLOCKED_RESPONSE


@pytest.mark.asyncio
async def test_empty_text_passes():
    """Empty/whitespace text should pass without calling API."""
    result = await check_content(
        text="   ",
        openai_api_key=FAKE_API_KEY,
        relationship="daughter",
    )
    assert result["safe"] is True


@pytest.mark.asyncio
async def test_no_api_key_passes():
    """Missing API key should pass without calling API."""
    result = await check_content(
        text="Hello",
        openai_api_key="",
        relationship="daughter",
    )
    assert result["safe"] is True


# ── Threshold correctness ──────────────────────────────────

def test_child_thresholds_stricter_than_default():
    """Every child threshold should be <= the default threshold."""
    for category in CHILD_THRESHOLDS:
        assert category in DEFAULT_THRESHOLDS, f"Missing category in defaults: {category}"
        assert CHILD_THRESHOLDS[category] <= DEFAULT_THRESHOLDS[category], (
            f"Child threshold for {category} ({CHILD_THRESHOLDS[category]}) "
            f"is less strict than default ({DEFAULT_THRESHOLDS[category]})"
        )
