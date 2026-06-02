"""
Custom Presidio entity recognizers for Indian legal text.

WHY: Generic Presidio recognizers (PERSON, ORG, EMAIL, etc.) miss Indian
legal identifiers such as case numbers and matter IDs, and would naively
anonymize court names — breaking citation accuracy. These recognizers fill
the gap without touching the standard NLP pipeline.

Design decisions:
- Court names are WHITELISTED (never anonymized) to preserve citation integrity.
  A pseudonymized "ORGANIZATION_0001 v. ORGANIZATION_0002" in a filing is
  professionally embarrassing and legally meaningless.
- Case numbers use Indian court filing conventions as regex patterns.
- Only LOCATION entities that look like postal addresses are anonymized;
  city/state names used in jurisdiction references are left intact.
"""
from __future__ import annotations

import re
from typing import List, Optional

# Presidio is an optional dependency (pip install lexagent[pii]).
# Imports are deferred so the module loads cleanly without it.
try:
    from presidio_analyzer import EntityRecognizer, RecognizerResult
    from presidio_analyzer.nlp_engine import NlpArtifacts
    _PRESIDIO_AVAILABLE = True
except ImportError:
    _PRESIDIO_AVAILABLE = False
    EntityRecognizer = object  # type: ignore[assignment,misc]
    RecognizerResult = object  # type: ignore[assignment]
    NlpArtifacts = object  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Whitelist: court names that must NEVER be pseudonymized
# ---------------------------------------------------------------------------

INDIAN_COURT_WHITELIST: frozenset[str] = frozenset({
    "Supreme Court of India",
    "Supreme Court",
    "High Court",
    "High Court of Delhi",
    "Delhi High Court",
    "Bombay High Court",
    "High Court of Bombay",
    "Calcutta High Court",
    "High Court of Calcutta",
    "Madras High Court",
    "High Court of Madras",
    "Allahabad High Court",
    "High Court of Allahabad",
    "Kerala High Court",
    "High Court of Kerala",
    "Karnataka High Court",
    "High Court of Karnataka",
    "Rajasthan High Court",
    "Punjab and Haryana High Court",
    "Gujarat High Court",
    "Orissa High Court",
    "Gauhati High Court",
    "Himachal Pradesh High Court",
    "Jharkhand High Court",
    "Chhattisgarh High Court",
    "Uttarakhand High Court",
    "Manipur High Court",
    "Tripura High Court",
    "Meghalaya High Court",
    "Sikkim High Court",
    "National Company Law Tribunal",
    "NCLT",
    "NCLAT",
    "National Consumer Disputes Redressal Commission",
    "NCDRC",
    "Securities Appellate Tribunal",
    "SAT",
    "Income Tax Appellate Tribunal",
    "ITAT",
    "Central Administrative Tribunal",
    "CAT",
    "Armed Forces Tribunal",
    "National Green Tribunal",
    "NGT",
    "Debt Recovery Tribunal",
    "DRT",
    "District Court",
    "Sessions Court",
    "Magistrate Court",
    "Family Court",
    "Labour Court",
    "Industrial Tribunal",
    "Consumer Forum",
    "Lok Adalat",
})


# ---------------------------------------------------------------------------
# Regex patterns for Indian case identifiers
# ---------------------------------------------------------------------------

# Matches: "W.P. 1234/2024", "WP(C) 567/2023", "SLP (Civil) 890/2024",
#          "Crl.A. 12/2023", "C.A. 3456 of 2021", "IA No. 78/2024"
_CASE_NUMBER_PATTERNS = [
    # Writ petitions and SLPs
    r"\bW\.?P\.?\s*\(?[A-Za-z]*\)?\s*\d+\s*(?:/|of)\s*\d{4}\b",
    r"\bSLP\s*\(?[A-Za-z]*\)?\s*\d+\s*(?:/|of)\s*\d{4}\b",
    # Criminal and civil appeals
    r"\bCr[lim]*\.?\s*[AP]\.?\s*\d+\s*(?:/|of)\s*\d{4}\b",
    r"\bC\.?A\.?\s*\d+\s*(?:/|of)\s*\d{4}\b",
    # Interlocutory applications and miscellaneous
    r"\bI\.?A\.?\s*(?:No\.?\s*)?\d+\s*(?:/|of)\s*\d{4}\b",
    r"\bM\.?A\.?\s*\d+\s*(?:/|of)\s*\d{4}\b",
    # Original suits and Company petitions
    r"\bO\.?S\.?\s*\d+\s*(?:/|of)\s*\d{4}\b",
    r"\bC\.?P\.?\s*\d+\s*(?:/|of)\s*\d{4}\b",
    # Generic NN/YYYY pattern as fallback (4+ digit year)
    r"\b\d{1,5}\s*/\s*(?:19|20)\d{2}\b",
]

_CASE_NUMBER_RE = re.compile(
    "|".join(f"(?:{p})" for p in _CASE_NUMBER_PATTERNS),
    re.IGNORECASE,
)

# LexAgent internal matter IDs: "matter_abc123", "matter_xxxxxxxx"
_MATTER_ID_RE = re.compile(r"\bmatter_[a-f0-9]{8,}\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Recognizer implementations
# ---------------------------------------------------------------------------

if _PRESIDIO_AVAILABLE:

    class CaseNumberRecognizer(EntityRecognizer):
        """Recognizes Indian court case numbers for pseudonymization."""

        SUPPORTED_ENTITY = "IN_CASE_NUMBER"

        def __init__(self) -> None:
            super().__init__(
                supported_entities=[self.SUPPORTED_ENTITY],
                name="CaseNumberRecognizer",
                supported_language="en",
            )

        def load(self) -> None:
            pass

        def analyze(
            self,
            text: str,
            entities: List[str],
            nlp_artifacts: Optional[NlpArtifacts] = None,
        ) -> List[RecognizerResult]:
            if self.SUPPORTED_ENTITY not in entities:
                return []
            results = []
            for m in _CASE_NUMBER_RE.finditer(text):
                results.append(
                    RecognizerResult(
                        entity_type=self.SUPPORTED_ENTITY,
                        start=m.start(),
                        end=m.end(),
                        score=0.85,
                    )
                )
            return results

    class MatterIdRecognizer(EntityRecognizer):
        """Recognizes LexAgent internal matter_xxx IDs for pseudonymization."""

        SUPPORTED_ENTITY = "LEX_MATTER_ID"

        def __init__(self) -> None:
            super().__init__(
                supported_entities=[self.SUPPORTED_ENTITY],
                name="MatterIdRecognizer",
                supported_language="en",
            )

        def load(self) -> None:
            pass

        def analyze(
            self,
            text: str,
            entities: List[str],
            nlp_artifacts: Optional[NlpArtifacts] = None,
        ) -> List[RecognizerResult]:
            if self.SUPPORTED_ENTITY not in entities:
                return []
            results = []
            for m in _MATTER_ID_RE.finditer(text):
                results.append(
                    RecognizerResult(
                        entity_type=self.SUPPORTED_ENTITY,
                        start=m.start(),
                        end=m.end(),
                        score=0.95,
                    )
                )
            return results

else:
    # Stub classes when Presidio is not installed — allow imports to succeed
    # so tests that don't exercise anonymization still run cleanly.
    class CaseNumberRecognizer:  # type: ignore[no-redef]
        pass

    class MatterIdRecognizer:  # type: ignore[no-redef]
        pass
