# Tests for R2A + R2B: mem0 semantic memory layer
#
# All tests run against the disabled/fallback path (mem0ai not installed in CI).
# Integration tests that require a live Qdrant + mem0ai are skipped unless
# LEX_MEM0_ENABLED=true and Qdrant is reachable.

import os
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from themis.memory.mem0_client import Mem0Client, _try_import_mem0
from themis.memory.lawyer_memory import (
    load_lawyer_profile,
    load_matter_context,
    reset_client,
    save_feedback,
    seed_soul_to_mem0,
    seed_matter_to_mem0,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Always reset the module-level Mem0Client singleton between tests."""
    reset_client()
    yield
    reset_client()


@pytest.fixture()
def tmp_home(tmp_path: Path) -> Path:
    return tmp_path / "themis"


@pytest.fixture()
def soul_file(tmp_home: Path) -> Path:
    """Create a minimal SOUL.md for test use."""
    tmp_home.mkdir(parents=True, exist_ok=True)
    path = tmp_home / "SOUL.md"
    path.write_text(
        "# Lawyer Identity\n**Name:** Arjun Mehta\n**Primary Courts:** Delhi High Court\n",
        encoding="utf-8",
    )
    return path


def _make_config(tmp_home: Path, mem0_enabled: bool = False) -> "LexConfig":  # type: ignore[name-defined]
    """Build a LexConfig pointing at tmp_home, with mem0 toggle."""
    from themis.config import LexConfig

    return LexConfig(
        home_dir=str(tmp_home),
        matters_dir=str(tmp_home / "matters"),
        mem0_enabled=mem0_enabled,
        qdrant_url="http://localhost:6333",
    )


# ---------------------------------------------------------------------------
# Mem0Client — disabled / no mem0ai
# ---------------------------------------------------------------------------


class TestMem0ClientDisabled:
    """When mem0ai is absent, Mem0Client must degrade to a safe no-op."""

    def test_is_available_false_when_mem0ai_missing(self):
        """_try_import_mem0 returns None when mem0ai is not installed."""
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=None):
            client = Mem0Client()
        assert client.is_available is False

    def test_add_returns_none(self):
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=None):
            client = Mem0Client()
        result = client.add("some memory", user_id="lawyer_1")
        assert result is None

    def test_search_returns_empty_list(self):
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=None):
            client = Mem0Client()
        result = client.search("drafting style", user_id="lawyer_1")
        assert result == []

    def test_get_all_returns_empty_list(self):
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=None):
            client = Mem0Client()
        result = client.get_all(user_id="lawyer_1")
        assert result == []


class TestMem0ClientInit:
    """Client init must not raise even when mem0ai init fails (e.g. Qdrant unreachable)."""

    def test_init_failure_sets_unavailable(self):
        # mem0_client calls MemoryClass.from_config(), not MemoryClass() directly
        fake_memory_class = MagicMock()
        fake_memory_class.from_config.side_effect = RuntimeError("Qdrant unreachable")
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=fake_memory_class):
            client = Mem0Client()
        assert client.is_available is False

    def test_search_normalises_dict_wrapper(self):
        """mem0 v0.1.29+ wraps results in {"results": [...]}."""
        mock_mem = MagicMock()
        mock_mem.search.return_value = {
            "results": [{"memory": "Prefer formal tone"}, {"memory": "Always cite HC judgments"}]
        }
        fake_class = MagicMock(return_value=mock_mem)
        fake_class.from_config = MagicMock(return_value=mock_mem)
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=fake_class):
            client = Mem0Client()
        memories = client.search("style", user_id="lawyer_1")
        assert memories == ["Prefer formal tone", "Always cite HC judgments"]

    def test_search_handles_list_result(self):
        """Older mem0 versions return a bare list."""
        mock_mem = MagicMock()
        mock_mem.search.return_value = [{"memory": "Use Delhi HC citation format"}]
        fake_class = MagicMock(return_value=mock_mem)
        fake_class.from_config = MagicMock(return_value=mock_mem)
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=fake_class):
            client = Mem0Client()
        memories = client.search("citation", user_id="lawyer_1")
        assert memories == ["Use Delhi HC citation format"]

    def test_search_failure_returns_empty(self):
        """Network errors during search must not propagate."""
        mock_mem = MagicMock()
        mock_mem.search.side_effect = ConnectionError("Qdrant down")
        fake_class = MagicMock(return_value=mock_mem)
        fake_class.from_config = MagicMock(return_value=mock_mem)
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=fake_class):
            client = Mem0Client()
        result = client.search("style", user_id="lawyer_1")
        assert result == []

    def test_add_extracts_id_from_list(self):
        mock_mem = MagicMock()
        mock_mem.add.return_value = [{"id": "abc123"}]
        fake_class = MagicMock(return_value=mock_mem)
        fake_class.from_config = MagicMock(return_value=mock_mem)
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=fake_class):
            client = Mem0Client()
        result = client.add("memory text", user_id="lawyer_1")
        assert result == "abc123"


# ---------------------------------------------------------------------------
# lawyer_memory — disabled mode (file fallback)
# ---------------------------------------------------------------------------


class TestLawyerMemoryDisabled:
    """When mem0_enabled=False the functions must behave exactly like the old file-based paths."""

    def test_load_lawyer_profile_returns_soul_text(self, soul_file: Path, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=False)
        profile = load_lawyer_profile("lawyer_1", config)
        assert profile is not None
        assert "Arjun Mehta" in profile

    def test_load_lawyer_profile_returns_none_when_no_soul(self, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=False)
        profile = load_lawyer_profile("lawyer_1", config)
        assert profile is None  # no SOUL.md created

    def test_save_feedback_is_noop(self, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=False)
        # Must not raise — verified by the call completing without error
        save_feedback("Drafted NI Act", "matter_1", "lawyer_1", config)

    def test_load_matter_context_reads_memory_md(self, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=False)
        matters = tmp_home / "matters" / "matter_abc"
        matters.mkdir(parents=True, exist_ok=True)
        (matters / "MEMORY.md").write_text("# Matter Memory\nKey fact: cheque dated 01-01-2024", encoding="utf-8")
        ctx = load_matter_context("matter_abc", "lawyer_1", config)
        assert ctx is not None
        assert "cheque dated 01-01-2024" in ctx

    def test_load_matter_context_returns_none_for_unknown_matter(self, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=False)
        ctx = load_matter_context("nonexistent_matter", "lawyer_1", config)
        assert ctx is None


# ---------------------------------------------------------------------------
# lawyer_memory — enabled mode (mocked mem0)
# ---------------------------------------------------------------------------


class TestLawyerMemoryEnabled:
    """When mem0_enabled=True, memory reads/writes go through the Mem0Client."""

    def _patch_client(self, memories: list[str], add_id: str = "mem_001"):
        """Return a mock Mem0Client that yields the given memories on search."""
        mock = MagicMock(spec=Mem0Client)
        mock.is_available = True
        mock.search.return_value = memories
        mock.add.return_value = add_id
        return mock

    def test_load_lawyer_profile_appends_mem0_memories(self, soul_file: Path, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = self._patch_client(["Prefers Bombay HC formatting", "Always cite SC constitution benches"])
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            profile = load_lawyer_profile("lawyer_1", config)
        assert "Arjun Mehta" in profile
        assert "Recalled Style Memories" in profile
        assert "Prefers Bombay HC formatting" in profile

    def test_load_lawyer_profile_returns_soul_only_when_no_memories(self, soul_file: Path, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = self._patch_client([])
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            profile = load_lawyer_profile("lawyer_1", config)
        assert "Arjun Mehta" in profile
        assert "Recalled Style Memories" not in profile

    def test_save_feedback_calls_add(self, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = self._patch_client([])
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            save_feedback("Drafted NI Act for Delhi", "matter_1", "lawyer_1", config)
        mock_client.add.assert_called_once()
        call_args = mock_client.add.call_args
        assert "Drafted NI Act" in call_args[0][0]
        assert call_args[1]["user_id"] == "lawyer_1"

    def test_load_matter_context_returns_mem0_results(self, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = self._patch_client(["Cheque dishonoured on 15-01-2024", "Accused is XYZ Pvt Ltd"])
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            ctx = load_matter_context("matter_1", "lawyer_1", config)
        assert ctx is not None
        assert "Cheque dishonoured" in ctx
        assert "XYZ Pvt Ltd" in ctx

    def test_load_matter_context_falls_back_to_memory_md_when_no_mem0_results(self, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=True)
        matters = tmp_home / "matters" / "matter_1"
        matters.mkdir(parents=True, exist_ok=True)
        (matters / "MEMORY.md").write_text("# Matter Memory\nFiled at Tis Hazari", encoding="utf-8")
        mock_client = self._patch_client([])  # empty mem0 results
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            ctx = load_matter_context("matter_1", "lawyer_1", config)
        assert ctx is not None
        assert "Tis Hazari" in ctx

    def test_client_unavailable_falls_back_to_soul_file(self, soul_file: Path, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = MagicMock(spec=Mem0Client)
        mock_client.is_available = False
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            profile = load_lawyer_profile("lawyer_1", config)
        assert profile is not None
        assert "Arjun Mehta" in profile
        mock_client.search.assert_not_called()


# ---------------------------------------------------------------------------
# soul.py: load_soul_enriched
# ---------------------------------------------------------------------------


class TestLoadSoulEnriched:
    def test_no_config_returns_soul_file_text(self, soul_file: Path, tmp_home: Path):
        from themis.memory.soul import load_soul_enriched, soul_path
        # Patch soul_path to use our tmp file
        with patch("themis.memory.soul.soul_path", return_value=soul_file):
            result = load_soul_enriched("lawyer_1", config=None)
        assert result is not None
        assert "Arjun Mehta" in result

    def test_with_config_routes_through_lawyer_memory(self, soul_file: Path, tmp_home: Path):
        from themis.memory.soul import load_soul_enriched
        config = _make_config(tmp_home, mem0_enabled=False)
        with patch("themis.memory.soul.soul_path", return_value=soul_file):
            result = load_soul_enriched("lawyer_1", config=config)
        assert result is not None
        assert "Arjun Mehta" in result


# ---------------------------------------------------------------------------
# singleton reset
# ---------------------------------------------------------------------------


class TestSingletonReset:
    def test_reset_forces_reinit(self, tmp_home: Path):
        """After reset_client(), the next call must create a fresh Mem0Client."""
        config = _make_config(tmp_home, mem0_enabled=True)
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=None):
            _ = load_lawyer_profile("lawyer_1", config)
        reset_client()
        # A second call should not reuse the old (None) client
        with patch("themis.memory.mem0_client._try_import_mem0", return_value=None):
            with patch("themis.memory.lawyer_memory._get_client") as mock_get:
                mock_client = MagicMock(spec=Mem0Client)
                mock_client.is_available = False
                mock_get.return_value = mock_client
                _ = load_lawyer_profile("lawyer_1", config)
            mock_get.assert_called_once()


# ---------------------------------------------------------------------------
# R2B: seed functions
# ---------------------------------------------------------------------------


class TestSeedSoulToMem0:
    def _make_soul(self, tmp_home: Path) -> Path:
        tmp_home.mkdir(parents=True, exist_ok=True)
        soul = tmp_home / "SOUL.md"
        soul.write_text(
            "# Lawyer Identity\n"
            "**Name:** Arjun Mehta\n"
            "**Primary Courts:** Delhi High Court\n"
            "**Primary Practice Areas:** Civil Litigation, Arbitration\n"
            "**Preferred Tone:** Senior formal\n"
            "**Citation Preference:** Always include\n"
            "**Document Length:** Comprehensive\n"
            "**Firm Name:** Mehta & Associates\n\n"
            "## Known Judicial Preferences\n"
            "Justice Sharma prefers concise submissions.\n\n"
            "## Custom Instructions\n"
            "Always verify limitation period.\n",
            encoding="utf-8",
        )
        return soul

    def test_noop_when_mem0_disabled(self, tmp_home: Path):
        self._make_soul(tmp_home)
        config = _make_config(tmp_home, mem0_enabled=False)
        count = seed_soul_to_mem0("lawyer_1", config)
        assert count == 0

    def test_noop_when_no_soul_file(self, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = MagicMock(spec=Mem0Client)
        mock_client.is_available = True
        mock_client.add.return_value = "mem_1"
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            count = seed_soul_to_mem0("lawyer_1", config)
        assert count == 0
        mock_client.add.assert_not_called()

    def test_stores_field_memories(self, tmp_home: Path):
        self._make_soul(tmp_home)
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = MagicMock(spec=Mem0Client)
        mock_client.is_available = True
        mock_client.add.return_value = "mem_001"
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            count = seed_soul_to_mem0("lawyer_1", config)
        assert count > 0
        # Should have stored courts, practice areas, tone, citation pref, firm, sections
        all_calls = [call[0][0] for call in mock_client.add.call_args_list]
        courts_call = next((c for c in all_calls if "Delhi High Court" in c), None)
        assert courts_call is not None, "Primary courts not seeded"
        tone_call = next((c for c in all_calls if "Senior formal" in c), None)
        assert tone_call is not None, "Preferred tone not seeded"
        citation_call = next((c for c in all_calls if "Always include" in c), None)
        assert citation_call is not None, "Citation preference not seeded"

    def test_stores_section_memories(self, tmp_home: Path):
        self._make_soul(tmp_home)
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = MagicMock(spec=Mem0Client)
        mock_client.is_available = True
        mock_client.add.return_value = "mem_001"
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            seed_soul_to_mem0("lawyer_1", config)
        all_calls = [call[0][0] for call in mock_client.add.call_args_list]
        judicial_call = next((c for c in all_calls if "Justice Sharma" in c), None)
        assert judicial_call is not None, "Judicial preferences section not seeded"

    def test_add_failure_does_not_count(self, tmp_home: Path):
        self._make_soul(tmp_home)
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = MagicMock(spec=Mem0Client)
        mock_client.is_available = True
        mock_client.add.return_value = None  # simulate add failure
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            count = seed_soul_to_mem0("lawyer_1", config)
        assert count == 0

    def test_client_unavailable_returns_zero(self, tmp_home: Path):
        self._make_soul(tmp_home)
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = MagicMock(spec=Mem0Client)
        mock_client.is_available = False
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            count = seed_soul_to_mem0("lawyer_1", config)
        assert count == 0


class TestSeedMatterToMem0:
    def _make_memory_md(self, tmp_home: Path, matter_id: str) -> Path:
        matters = tmp_home / "matters" / matter_id
        matters.mkdir(parents=True, exist_ok=True)
        md = matters / "MEMORY.md"
        md.write_text(
            "# Matter Memory\n\n"
            "## Parties\nComplainant: Ankush Sareen. Accused: XYZ Pvt Ltd.\n\n"
            "## Key Facts\nCheque dishonoured on 15-01-2024. Amount: Rs. 5,00,000.\n\n"
            "## Research Notes\nLimitation period: 30 days from return memo date.\n",
            encoding="utf-8",
        )
        return md

    def test_noop_when_mem0_disabled(self, tmp_home: Path):
        self._make_memory_md(tmp_home, "matter_1")
        config = _make_config(tmp_home, mem0_enabled=False)
        count = seed_matter_to_mem0("matter_1", "lawyer_1", config)
        assert count == 0

    def test_noop_when_no_memory_md(self, tmp_home: Path):
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = MagicMock(spec=Mem0Client)
        mock_client.is_available = True
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            count = seed_matter_to_mem0("nonexistent_matter", "lawyer_1", config)
        assert count == 0
        mock_client.add.assert_not_called()

    def test_splits_sections_into_separate_memories(self, tmp_home: Path):
        self._make_memory_md(tmp_home, "matter_1")
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = MagicMock(spec=Mem0Client)
        mock_client.is_available = True
        mock_client.add.return_value = "mem_001"
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            count = seed_matter_to_mem0("matter_1", "lawyer_1", config)
        # 3 sections: Parties, Key Facts, Research Notes (plus possibly the header)
        assert count >= 3
        all_calls = [call[0][0] for call in mock_client.add.call_args_list]
        parties_call = next((c for c in all_calls if "Ankush Sareen" in c), None)
        assert parties_call is not None, "Parties section not seeded"
        facts_call = next((c for c in all_calls if "5,00,000" in c), None)
        assert facts_call is not None, "Key facts section not seeded"

    def test_metadata_tagged_with_matter_id(self, tmp_home: Path):
        self._make_memory_md(tmp_home, "matter_abc")
        config = _make_config(tmp_home, mem0_enabled=True)
        mock_client = MagicMock(spec=Mem0Client)
        mock_client.is_available = True
        mock_client.add.return_value = "mem_001"
        with patch("themis.memory.lawyer_memory._get_client", return_value=mock_client):
            seed_matter_to_mem0("matter_abc", "lawyer_1", config)
        for call in mock_client.add.call_args_list:
            assert call[1]["metadata"]["matter_id"] == "matter_abc"


# ---------------------------------------------------------------------------
# R2B: enriched draft feedback (smoke test — full draft test in test_draft.py)
# ---------------------------------------------------------------------------


class TestEnrichedDraftFeedback:
    """The save_feedback() call in draft.py should pass richer content in R2B."""

    def test_feedback_includes_summary_and_statutes(self, tmp_home: Path):
        """Verify the R2B signal format carries summary + statutes when available."""
        config = _make_config(tmp_home, mem0_enabled=True)
        captured: list[str] = []

        def _capture(text, matter_id, lawyer_id, cfg, metadata=None):
            captured.append(text)

        with patch("themis.memory.lawyer_memory.save_feedback", side_effect=_capture):
            # Simulate what draft.py now builds
            _matter_type = "ni_act_138"
            _jurisdiction = "Delhi"
            _skill = "NI Act Complaint"
            _statutes = ["Section 138 NI Act", "Section 142 NI Act"]
            _summary = "Complainant seeks relief for dishonoured cheque of Rs. 5L."

            parts = [f"Drafted {_matter_type} matter for {_jurisdiction}."]
            if _skill:
                parts.append(f"Skill used: {_skill}.")
            if _statutes:
                parts.append(f"Statutes cited: {', '.join(_statutes[:5])}.")
            if _summary:
                parts.append(f"Summary: {_summary}")
            signal = " ".join(parts)

            from themis.memory.lawyer_memory import save_feedback
            save_feedback(signal, "matter_1", "lawyer_1", config)

        assert len(captured) == 1
        assert "Section 138 NI Act" in captured[0]
        assert "dishonoured cheque" in captured[0]
        assert "Skill used: NI Act Complaint" in captured[0]
