"""
Tests for the PII anonymization gateway.

These tests mock Presidio so they run without the optional [pii] extras installed.
The test suite validates:
  - Anonymizer pseudonymizes PERSON entities in user/assistant messages
  - System messages are never touched
  - restore() exactly reverses anonymization
  - is_document_context=True bypasses the whole pipeline
  - Privileged matters bypass anonymization
  - Court names are NOT anonymized (whitelist)
  - InferenceGateway routes through anonymization only when enabled
  - InferenceGateway falls through to direct litellm when disabled
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexagent.config import LexConfig
from lexagent.gateway.anonymizer import LegalAnonymizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cfg(**kwargs) -> LexConfig:
    base = dict(
        anthropic_api_key="test-key",
        anonymization_enabled=False,
        anonymization_privileged_matters=[],
    )
    base.update(kwargs)
    return LexConfig(**base)


# ---------------------------------------------------------------------------
# LegalAnonymizer unit tests (with mocked Presidio)
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_presidio(monkeypatch):
    """
    Monkeypatch Presidio classes on the anonymizer module so tests run
    without the optional [pii] dependencies installed.
    """
    fake_result = MagicMock()
    fake_result.entity_type = "PERSON"
    fake_result.start = 7
    fake_result.end = 18
    fake_result.score = 0.9

    analyzer = MagicMock()
    analyzer.analyze.return_value = [fake_result]

    anon_engine = MagicMock()

    def fake_ensure_loaded(self):
        self._analyzer = analyzer
        self._anon_engine = anon_engine

    monkeypatch.setattr(LegalAnonymizer, "_ensure_loaded", fake_ensure_loaded)
    return analyzer, anon_engine


def test_anonymize_user_message(mock_presidio):
    """User message content gets pseudonymized."""
    anon = LegalAnonymizer()
    messages = [{"role": "user", "content": "Hello, Rahul Sharma is the plaintiff."}]
    result_msgs, pmap = anon.anonymize(messages)

    assert result_msgs[0]["role"] == "user"
    # Original text was modified (pseudonym inserted)
    assert result_msgs[0]["content"] != messages[0]["content"]
    # Pseudonym map is populated
    assert len(pmap) > 0


def test_system_message_never_anonymized(mock_presidio):
    """System prompt content is never touched — protects prompt caching."""
    anon = LegalAnonymizer()
    system_text = "You are a legal assistant. Firm: LexCorp."
    messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": "Advise on the case."},
    ]
    result_msgs, _pmap = anon.anonymize(messages)
    assert result_msgs[0]["content"] == system_text


def test_restore_reverses_anonymization(mock_presidio):
    """restore() exactly recovers original text from a pseudonym map."""
    anon = LegalAnonymizer()
    messages = [{"role": "user", "content": "Hello, Rahul Sharma is here."}]
    result_msgs, pmap = anon.anonymize(messages)

    # Restore the first (and only) pseudonym back
    restored = anon.restore(result_msgs[0]["content"], pmap)
    # The restored text should contain the original entity value
    for original in pmap.values():
        assert original in restored


def test_empty_message_unchanged(mock_presidio):
    """Empty content strings pass through without modification."""
    anon = LegalAnonymizer()
    messages = [{"role": "user", "content": ""}]
    result_msgs, pmap = anon.anonymize(messages)
    assert result_msgs[0]["content"] == ""
    assert pmap == {}


def test_non_string_content_unchanged(mock_presidio):
    """Non-string content (e.g. content blocks) passes through unchanged."""
    anon = LegalAnonymizer()
    messages = [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
    result_msgs, pmap = anon.anonymize(messages)
    assert result_msgs[0]["content"] == [{"type": "text", "text": "hello"}]


def test_court_names_not_anonymized():
    """
    Court names in the whitelist must survive anonymization unchanged.
    We test the whitelist set directly since Presidio is mocked.
    """
    from lexagent.gateway.recognizers import INDIAN_COURT_WHITELIST
    assert "Supreme Court of India" in INDIAN_COURT_WHITELIST
    assert "Delhi High Court" in INDIAN_COURT_WHITELIST
    assert "National Company Law Tribunal" in INDIAN_COURT_WHITELIST


def test_case_number_regex():
    """Indian case number patterns match the regex."""
    import re
    from lexagent.gateway.recognizers import _CASE_NUMBER_RE

    cases = [
        "W.P. 1234/2024",
        "WP(C) 567/2023",
        "SLP (Civil) 890/2024",
        "Crl.A. 12/2023",
        "C.A. 3456 of 2021",
        "IA No. 78/2024",
    ]
    for c in cases:
        assert _CASE_NUMBER_RE.search(c), f"Pattern not matched: {c!r}"


def test_matter_id_regex():
    """LexAgent matter IDs match the regex."""
    from lexagent.gateway.recognizers import _MATTER_ID_RE
    assert _MATTER_ID_RE.search("matter_abc12345")
    assert not _MATTER_ID_RE.search("matter_ab")  # too short


# ---------------------------------------------------------------------------
# InferenceGateway routing tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gateway_disabled_calls_litellm_directly():
    """When anonymization is disabled, gateway calls litellm without any PII work."""
    cfg = _make_cfg(anonymization_enabled=False)
    messages = [{"role": "user", "content": "Draft a notice for Rahul Sharma."}]

    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message.content = "Here is the notice."
    fake_response.choices[0].message.tool_calls = None
    fake_response.usage.prompt_tokens = 10
    fake_response.usage.completion_tokens = 20

    with patch("lexagent.gateway.inference.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = fake_response
        from lexagent.gateway.inference import InferenceGateway
        gw = InferenceGateway()
        result = await gw.call(messages, cfg, matter_id=None, is_document_context=False)

    assert result["content"] == "Here is the notice."
    # Presidio never called — gateway was disabled
    mock_llm.assert_called_once()
    call_kwargs = mock_llm.call_args[1]
    # Messages passed to litellm are unmodified
    assert call_kwargs["messages"][0]["content"] == "Draft a notice for Rahul Sharma."


@pytest.mark.asyncio
async def test_gateway_is_document_context_bypasses_anonymization(mock_presidio):
    """is_document_context=True skips anonymization regardless of config."""
    cfg = _make_cfg(anonymization_enabled=True)
    messages = [{"role": "user", "content": "Rahul Sharma v. ABC Corp — what happened on 01/01/2020?"}]

    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message.content = "On that date..."
    fake_response.choices[0].message.tool_calls = None
    fake_response.usage.prompt_tokens = 5
    fake_response.usage.completion_tokens = 3

    analyzer, _ = mock_presidio
    analyzer.analyze.reset_mock()

    with patch("lexagent.gateway.inference.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = fake_response
        from lexagent.gateway.inference import InferenceGateway
        gw = InferenceGateway()
        # Bypass LegalAnonymizer loading entirely for this test
        gw._anonymizer = MagicMock()
        result = await gw.call(
            messages, cfg, matter_id=None, is_document_context=True
        )

    # Anonymizer.anonymize should never have been called
    gw._anonymizer.anonymize.assert_not_called()
    assert result["content"] == "On that date..."


@pytest.mark.asyncio
async def test_gateway_privileged_matter_bypasses_anonymization():
    """Matter IDs in anonymization_privileged_matters skip anonymization."""
    cfg = _make_cfg(
        anonymization_enabled=True,
        anonymization_privileged_matters=["matter_abc123"],
    )
    messages = [{"role": "user", "content": "Rahul Sharma is the petitioner."}]

    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message.content = "Noted."
    fake_response.choices[0].message.tool_calls = None
    fake_response.usage.prompt_tokens = 5
    fake_response.usage.completion_tokens = 1

    with patch("lexagent.gateway.inference.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = fake_response
        from lexagent.gateway.inference import InferenceGateway
        gw = InferenceGateway()
        gw._anonymizer = MagicMock()
        result = await gw.call(
            messages, cfg, matter_id="matter_abc123", is_document_context=False
        )

    gw._anonymizer.anonymize.assert_not_called()
    assert result["content"] == "Noted."


@pytest.mark.asyncio
async def test_gateway_enabled_anonymizes_then_restores(mock_presidio):
    """
    With anonymization enabled, messages are anonymized before LLM call
    and pseudonyms in the response are restored.
    """
    cfg = _make_cfg(anonymization_enabled=True)

    original_content = "Hello, Rahul Sharma is the plaintiff."
    messages = [{"role": "user", "content": original_content}]

    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    # Simulate LLM echoing a pseudonym back in its response
    fake_response.choices[0].message.content = "I see PERSON_0001 is the plaintiff."
    fake_response.choices[0].message.tool_calls = None
    fake_response.usage.prompt_tokens = 10
    fake_response.usage.completion_tokens = 8

    with patch("lexagent.gateway.inference.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = fake_response

        # Inject a controlled anonymizer that returns predictable pseudonyms
        mock_anon = MagicMock()
        mock_anon.anonymize.return_value = (
            [{"role": "user", "content": "Hello, PERSON_0001 is the plaintiff."}],
            {"PERSON_0001": "Rahul Sharma"},
        )
        mock_anon.restore.return_value = "I see Rahul Sharma is the plaintiff."

        from lexagent.gateway.inference import InferenceGateway
        gw = InferenceGateway()
        gw._anonymizer = mock_anon

        result = await gw.call(
            messages, cfg, matter_id="matter_test01", is_document_context=False
        )

    # Anonymize was called with original messages
    mock_anon.anonymize.assert_called_once()
    # LLM received pseudonymized content, not original
    sent_msgs = mock_llm.call_args[1]["messages"]
    assert "PERSON_0001" in sent_msgs[0]["content"]
    assert "Rahul Sharma" not in sent_msgs[0]["content"]
    # Response had pseudonyms restored
    assert result["content"] == "I see Rahul Sharma is the plaintiff."


# ---------------------------------------------------------------------------
# _should_anonymize logic
# ---------------------------------------------------------------------------

def test_should_anonymize_disabled():
    from lexagent.gateway.inference import InferenceGateway
    gw = InferenceGateway()
    cfg = _make_cfg(anonymization_enabled=False)
    assert gw._should_anonymize(cfg, matter_id=None, is_document_context=False) is False


def test_should_anonymize_document_context():
    from lexagent.gateway.inference import InferenceGateway
    gw = InferenceGateway()
    cfg = _make_cfg(anonymization_enabled=True)
    assert gw._should_anonymize(cfg, matter_id=None, is_document_context=True) is False


def test_should_anonymize_privileged_matter():
    from lexagent.gateway.inference import InferenceGateway
    gw = InferenceGateway()
    cfg = _make_cfg(
        anonymization_enabled=True,
        anonymization_privileged_matters=["matter_priv01"],
    )
    assert gw._should_anonymize(cfg, matter_id="matter_priv01", is_document_context=False) is False


def test_should_anonymize_normal_case():
    from lexagent.gateway.inference import InferenceGateway
    gw = InferenceGateway()
    cfg = _make_cfg(anonymization_enabled=True)
    assert gw._should_anonymize(cfg, matter_id="matter_norm01", is_document_context=False) is True
