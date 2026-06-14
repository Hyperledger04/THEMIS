"""
PII anonymization engine for Themis inference calls.

Pseudonymizes client-identifying entities in LLM message content before
the text leaves the deployment boundary, then restores originals in the
response. Zero overhead when anonymization is disabled.

Key design rules (derived from LQ.AI architecture + Indian legal requirements):
  1. ONLY role=user and role=assistant messages are anonymized.
     role=system prompts contain firm strategy — never client PII — and must
     stay intact so prompt caching continues to work.
  2. is_document_context=True bypasses anonymization entirely.
     Retrieved document text must preserve exact citation text for the
     citation verification pipeline.
  3. Privileged matters bypass anonymization when the matter ID appears in
     cfg.anonymization_privileged_matters.
  4. Court names are whitelisted and never replaced — see recognizers.py.
  5. Pseudonyms are stable within a session: PERSON_0001 always refers to
     the same entity across the message sequence being anonymized.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from themis.gateway.recognizers import INDIAN_COURT_WHITELIST


# Type alias: maps pseudonym token → original text
PseudonymMap = dict[str, str]

_WHITELIST_RE = re.compile(
    "|".join(re.escape(name) for name in sorted(INDIAN_COURT_WHITELIST, key=len, reverse=True)),
    re.IGNORECASE,
)


class LegalAnonymizer:
    """
    Presidio-backed PII anonymizer with Indian legal entity support.

    Lazy-initializes Presidio on first call so startup is fast when
    anonymization is disabled (cfg.anonymization_enabled=False).
    """

    def __init__(self) -> None:
        self._analyzer: Any = None
        self._anon_engine: Any = None
        self._counters: dict[str, int] = defaultdict(int)

    def _ensure_loaded(self) -> None:
        if self._analyzer is not None:
            return
        try:
            from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
            from presidio_anonymizer import AnonymizerEngine
            from themis.gateway.recognizers import CaseNumberRecognizer, MatterIdRecognizer
        except ImportError as e:
            raise ImportError(
                "PII anonymization requires: pip install themis[pii]\n"
                "Then: python -m spacy download en_core_web_lg"
            ) from e

        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(languages=["en"])
        registry.add_recognizer(CaseNumberRecognizer())
        registry.add_recognizer(MatterIdRecognizer())

        self._analyzer = AnalyzerEngine(registry=registry)
        self._anon_engine = AnonymizerEngine()

    def _next_pseudonym(self, entity_type: str) -> str:
        """Return the next stable pseudonym for an entity type, e.g. PERSON_0001."""
        self._counters[entity_type] += 1
        label = entity_type.replace("IN_", "").replace("LEX_", "")
        return f"{label}_{self._counters[entity_type]:04d}"

    def _anonymize_text(self, text: str) -> tuple[str, PseudonymMap]:
        """Anonymize a single text string. Returns (anonymized_text, pseudonym_map)."""
        self._ensure_loaded()

        # Temporarily replace whitelisted court names with unique sentinels
        # so Presidio's ORG recognizer doesn't touch them.
        sentinels: dict[str, str] = {}
        protected = text
        for i, m in enumerate(_WHITELIST_RE.finditer(text)):
            sentinel = f"\x00COURT_{i}\x00"
            sentinels[sentinel] = m.group(0)
        for sentinel, original in sentinels.items():
            protected = protected.replace(original, sentinel, 1)

        # Run Presidio analysis
        entities = [
            "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
            "LOCATION", "ORGANIZATION",
            "IN_CASE_NUMBER", "LEX_MATTER_ID",
        ]
        results = self._analyzer.analyze(
            text=protected,
            entities=entities,
            language="en",
        )

        # Sort results in reverse order so we can replace without offset drift
        results = sorted(results, key=lambda r: r.start, reverse=True)

        pseudonym_map: PseudonymMap = {}
        anonymized = protected
        for result in results:
            original_chunk = anonymized[result.start:result.end]
            pseudonym = self._next_pseudonym(result.entity_type)
            pseudonym_map[pseudonym] = original_chunk
            anonymized = anonymized[: result.start] + pseudonym + anonymized[result.end :]

        # Restore court name sentinels
        for sentinel, original in sentinels.items():
            anonymized = anonymized.replace(sentinel, original)

        return anonymized, pseudonym_map

    def anonymize(
        self, messages: list[dict]
    ) -> tuple[list[dict], PseudonymMap]:
        """
        Anonymize user and assistant messages. System messages are never touched.

        Returns (anonymized_messages, merged_pseudonym_map).
        The pseudonym map covers all messages — pass it to restore().
        """
        merged_map: PseudonymMap = {}
        result: list[dict] = []
        for msg in messages:
            if msg.get("role") not in ("user", "assistant"):
                result.append(msg)
                continue
            content = msg.get("content", "")
            if not isinstance(content, str) or not content.strip():
                result.append(msg)
                continue
            anonymized_content, pmap = self._anonymize_text(content)
            merged_map.update(pmap)
            result.append({**msg, "content": anonymized_content})
        return result, merged_map

    def restore(self, text: str, pseudonym_map: PseudonymMap) -> str:
        """Replace all pseudonym tokens in text with their original values."""
        for pseudonym, original in pseudonym_map.items():
            text = text.replace(pseudonym, original)
        return text
