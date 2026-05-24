# WHY: Everything configurable lives here. This is the foundation for the future
# BYOK (Bring Your Own Key) and BYO-MCP (Bring Your Own MCP) frontend.
# Every field here maps to a future UI control — dropdown, toggle, text input.
# Never hardcode model names, API keys, or paths outside this class.

from typing import List, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class LexConfig(BaseSettings):
    # ----------------------------------------------------------------
    # LLM — BYOK (Bring Your Own Key)
    # Lawyers set their preferred provider and model in .env.
    # LiteLLM handles the rest — Claude, GPT, Gemini, Ollama, OpenRouter, etc.
    # ----------------------------------------------------------------
    # WHY: AliasChoices is the pydantic-settings v2 replacement for Field(env=...).
    # Each field accepts both the LEX_ prefixed name (documented in .env.example)
    # AND the bare field name so both forms work.
    anthropic_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key"))
    openai_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"))
    google_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("GOOGLE_API_KEY", "google_api_key"))
    openrouter_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("OPENROUTER_API_KEY", "openrouter_api_key"))

    default_model: str = Field("claude-sonnet-4-6", validation_alias=AliasChoices("LEX_MODEL", "default_model"))
    model_provider: str = Field("anthropic", validation_alias=AliasChoices("LEX_MODEL_PROVIDER", "model_provider"))
    # WHY: model_base_url enables local models (Ollama) and custom endpoints
    # without any code changes — just set the URL in .env.
    model_base_url: Optional[str] = Field(None, validation_alias=AliasChoices("LEX_MODEL_BASE_URL", "model_base_url"))

    # ----------------------------------------------------------------
    # Agent behaviour
    # ----------------------------------------------------------------
    max_iterations: int = Field(20, validation_alias=AliasChoices("LEX_MAX_ITERATIONS", "max_iterations"))
    auto_verify_citations: bool = Field(True, validation_alias=AliasChoices("LEX_AUTO_VERIFY_CITATIONS", "auto_verify_citations"))
    auto_save_matter: bool = Field(True, validation_alias=AliasChoices("LEX_AUTO_SAVE_MATTER", "auto_save_matter"))
    # WHY: Two-layer caching — Layer 1 (SQLiteCache, all providers) eliminates duplicate API calls.
    # Layer 2 (Anthropic cache_control) cuts server-side input token cost ~75% on the same session.
    enable_prompt_caching: bool = Field(True, validation_alias=AliasChoices("LEX_ENABLE_CACHING", "enable_prompt_caching"))

    # ----------------------------------------------------------------
    # Paths — all under ~/.lexagent by default
    # WHY: ~/.lexagent keeps lawyer data out of the project directory,
    # preventing accidental git commits of sensitive client matter data.
    # ----------------------------------------------------------------
    home_dir: str = Field("~/.lexagent", validation_alias=AliasChoices("LEX_HOME", "home_dir"))
    skills_dir: str = Field("~/.lexagent/skills", validation_alias=AliasChoices("LEX_SKILLS_DIR", "skills_dir"))
    matters_dir: str = Field("~/.lexagent/matters", validation_alias=AliasChoices("LEX_MATTERS_DIR", "matters_dir"))
    sessions_db: str = Field("~/.lexagent/sessions.db", validation_alias=AliasChoices("LEX_SESSIONS_DB", "sessions_db"))

    # ----------------------------------------------------------------
    # Legal Data Sources — BYOK / BYO-MCP
    # Each source has three backend modes:
    #   stub = mock data (default, works offline, for development)
    #   api  = direct HTTP with the lawyer's own API key
    #   mcp  = delegate to a configured MCP server
    # ----------------------------------------------------------------

    # Indian Kanoon
    kanoon_backend: str = Field("stub", validation_alias=AliasChoices("LEX_KANOON_BACKEND", "kanoon_backend"))
    kanoon_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("KANOON_API_KEY", "kanoon_api_key"))
    # WHY: kanoon_api_base_url is overridden in tests to point at a respx mock server
    # so no live HTTP calls are made. Production value is the official Kanoon API base.
    kanoon_api_base_url: str = Field("https://api.indiankanoon.org", validation_alias=AliasChoices("KANOON_API_BASE_URL", "kanoon_api_base_url"))
    kanoon_mcp_server: str = Field("E-courts", validation_alias=AliasChoices("LEX_KANOON_MCP", "kanoon_mcp_server"))
    # WHY: headless=False by default so lawyers can watch the browser during research.
    # Set LEX_KANOON_HEADLESS=true in .env for background / CI runs.
    kanoon_headless: bool = Field(False, validation_alias=AliasChoices("LEX_KANOON_HEADLESS", "kanoon_headless"))
    kanoon_max_results: int = Field(3, validation_alias=AliasChoices("LEX_KANOON_MAX_RESULTS", "kanoon_max_results"))

    # eCourts (Indian court case status)
    ecourts_backend: str = Field("stub", validation_alias=AliasChoices("LEX_ECOURTS_BACKEND", "ecourts_backend"))

    # CourtListener (US courts — global scope)
    courtlistener_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("COURTLISTENER_API_KEY", "courtlistener_api_key"))
    courtlistener_backend: str = Field("stub", validation_alias=AliasChoices("LEX_COURTLISTENER_BACKEND", "courtlistener_backend"))

    # ----------------------------------------------------------------
    # Phase 5 — Hybrid Retrieval (BM25 + TF-IDF vector)
    # ----------------------------------------------------------------
    # WHY: α weights exact-keyword BM25 (critical for Indian citation strings like
    # "AIR 1978 SC 597") against TF-IDF vector similarity for doctrine queries.
    retriever_bm25_weight: float = Field(0.4, validation_alias=AliasChoices("LEX_BM25_WEIGHT", "retriever_bm25_weight"))
    retriever_similarity_threshold: float = Field(0.35, validation_alias=AliasChoices("LEX_SIMILARITY_THRESHOLD", "retriever_similarity_threshold"))
    # Child chunks are used for precise match scoring; parent chunks go to the LLM.
    child_chunk_size: int = Field(256, validation_alias=AliasChoices("LEX_CHILD_CHUNK_SIZE", "child_chunk_size"))
    parent_chunk_size: int = Field(1024, validation_alias=AliasChoices("LEX_PARENT_CHUNK_SIZE", "parent_chunk_size"))

    # ----------------------------------------------------------------
    # Phase 6 — RAGFlow-Inspired Features
    # ----------------------------------------------------------------
    # 6a: PDF parsing — pdfplumber extracts text with layout awareness.
    # pdf_ocr_fallback enables Tesseract OCR for scanned PDFs (requires pytesseract).
    pdf_ocr_fallback: bool = Field(False, validation_alias=AliasChoices("LEX_PDF_OCR_FALLBACK", "pdf_ocr_fallback"))

    # 6b: Query expansion — expands BM25 queries with Indian legal synonyms.
    query_expansion_enabled: bool = Field(True, validation_alias=AliasChoices("LEX_QUERY_EXPANSION", "query_expansion_enabled"))

    # 6c: RAPTOR hierarchical summaries — clusters research findings and
    # generates LLM summaries per cluster for multi-hop doctrinal queries.
    # Off by default: each RAPTOR run costs one extra LLM call per cluster.
    raptor_enabled: bool = Field(False, validation_alias=AliasChoices("LEX_RAPTOR_ENABLED", "raptor_enabled"))
    raptor_max_layers: int = Field(2, validation_alias=AliasChoices("LEX_RAPTOR_MAX_LAYERS", "raptor_max_layers"))
    raptor_max_cluster_size: int = Field(5, validation_alias=AliasChoices("LEX_RAPTOR_MAX_CLUSTER_SIZE", "raptor_max_cluster_size"))

    # 6d: GraphRAG — extracts legal entities and builds a knowledge graph.
    # Off by default: adds entity-extraction pass over all research findings.
    graphrag_enabled: bool = Field(False, validation_alias=AliasChoices("LEX_GRAPHRAG_ENABLED", "graphrag_enabled"))

    # 6e: LLM re-ranker — cross-encoder re-ranking of retrieval results.
    # Off by default: adds one LLM call per retrieval.
    reranker_enabled: bool = Field(False, validation_alias=AliasChoices("LEX_RERANKER_ENABLED", "reranker_enabled"))

    # Individual tool toggles (for future UI enable/disable switches)
    enable_kanoon: bool = Field(True, validation_alias=AliasChoices("LEX_ENABLE_KANOON", "enable_kanoon"))
    enable_ecourts: bool = Field(True, validation_alias=AliasChoices("LEX_ENABLE_ECOURTS", "enable_ecourts"))
    enable_cause_list: bool = Field(False, validation_alias=AliasChoices("LEX_ENABLE_CAUSE_LIST", "enable_cause_list"))

    # ----------------------------------------------------------------
    # Messaging Gateways (Phase 7)
    # ----------------------------------------------------------------
    telegram_bot_token: Optional[str] = Field(None, validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "telegram_bot_token"))
    telegram_allowed_users: List[int] = Field(default_factory=list, validation_alias=AliasChoices("TELEGRAM_ALLOWED_USERS", "telegram_allowed_users"))

    # ----------------------------------------------------------------
    # Phase 9: Persistent Core — Postgres + Qdrant
    # WHY: LangGraph's AsyncPostgresSaver gives native state persistence,
    # human-in-the-loop, and time-travel for free. Qdrant gives per-matter
    # vector storage that survives restarts and accumulates across sessions.
    # ----------------------------------------------------------------
    # Postgres — reuses lexanodes/ DATABASE_URL if set, else standalone
    postgres_url: Optional[str] = Field(None, validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL", "postgres_url"))

    # Qdrant — local by default (no API key), cloud with key
    qdrant_url: str = Field("http://localhost:6333", validation_alias=AliasChoices("QDRANT_URL", "qdrant_url"))
    qdrant_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("QDRANT_API_KEY", "qdrant_api_key"))
    # WHY: all-MiniLM-L6-v2 is 22MB, runs fully local, and handles Indian
    # legal text well. Swap to "text-embedding-3-small" (OpenAI) via this flag.
    embedding_model: str = Field("all-MiniLM-L6-v2", validation_alias=AliasChoices("LEX_EMBEDDING_MODEL", "embedding_model"))
    embedding_dim: int = Field(384, validation_alias=AliasChoices("LEX_EMBEDDING_DIM", "embedding_dim"))
    # Whether to use Qdrant (persistent) or in-memory TF-IDF (stub/offline)
    qdrant_enabled: bool = Field(False, validation_alias=AliasChoices("LEX_QDRANT_ENABLED", "qdrant_enabled"))

    # ----------------------------------------------------------------
    # Phase 9: FastAPI Control Plane
    # ----------------------------------------------------------------
    control_plane_host: str = Field("0.0.0.0", validation_alias=AliasChoices("LEX_HOST", "control_plane_host"))
    control_plane_port: int = Field(8000, validation_alias=AliasChoices("LEX_PORT", "control_plane_port"))
    # JWT secret for API auth (gateways authenticate to the control plane)
    api_secret_key: Optional[str] = Field(None, validation_alias=AliasChoices("LEX_API_SECRET", "api_secret_key"))

    # ----------------------------------------------------------------
    # Phase 9: Multi-Tenant SaaS
    # WHY: Each firm gets isolated Qdrant collections and Postgres rows.
    # default_firm_id is used for single-lawyer mode (no auth required).
    # ----------------------------------------------------------------
    default_firm_id: str = Field("default", validation_alias=AliasChoices("LEX_FIRM_ID", "default_firm_id"))
    multi_tenant: bool = Field(False, validation_alias=AliasChoices("LEX_MULTI_TENANT", "multi_tenant"))

    # ----------------------------------------------------------------
    # Phase 9B: Voice AI Gateway
    # WHY: Voice is an opt-in gateway so existing deployments are
    # unaffected. Set LEX_VOICE_ENABLED=true to activate.
    # ----------------------------------------------------------------
    voice_gateway_enabled: bool = Field(False, validation_alias=AliasChoices("LEX_VOICE_ENABLED", "voice_gateway_enabled"))

    # STT (Speech-to-Text) backend: "whisper" | "deepgram" | "stub"
    # WHY: stub is the safe default — no API key required, tests pass offline.
    stt_backend: str = Field("stub", validation_alias=AliasChoices("LEX_STT_BACKEND", "stt_backend"))
    # BCP-47 language tag; en-IN gives best results for Indian English legal speech
    stt_language: str = Field("en-IN", validation_alias=AliasChoices("LEX_STT_LANGUAGE", "stt_language"))
    deepgram_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("DEEPGRAM_API_KEY", "deepgram_api_key"))

    # TTS (Text-to-Speech) backend: "google" | "elevenlabs" | "stub"
    tts_backend: str = Field("stub", validation_alias=AliasChoices("LEX_TTS_BACKEND", "tts_backend"))
    # Google Cloud TTS
    google_tts_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("GOOGLE_TTS_API_KEY", "google_tts_api_key"))
    # WHY: en-IN-Wavenet-D is a warm female Indian English voice — most natural
    # for a legal assistant. Lawyers can swap via LEX_GOOGLE_TTS_VOICE.
    google_tts_voice: str = Field("en-IN-Wavenet-D", validation_alias=AliasChoices("LEX_GOOGLE_TTS_VOICE", "google_tts_voice"))
    # ElevenLabs TTS
    elevenlabs_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("ELEVENLABS_API_KEY", "elevenlabs_api_key"))
    elevenlabs_voice_id: Optional[str] = Field(None, validation_alias=AliasChoices("ELEVENLABS_VOICE_ID", "elevenlabs_voice_id"))

    # Twilio phone gateway (optional — browser WebSocket works without Twilio)
    twilio_account_sid: Optional[str] = Field(None, validation_alias=AliasChoices("TWILIO_ACCOUNT_SID", "twilio_account_sid"))
    twilio_auth_token: Optional[str] = Field(None, validation_alias=AliasChoices("TWILIO_AUTH_TOKEN", "twilio_auth_token"))
    twilio_phone_number: Optional[str] = Field(None, validation_alias=AliasChoices("TWILIO_PHONE_NUMBER", "twilio_phone_number"))

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
