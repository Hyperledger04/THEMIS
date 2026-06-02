"""
04 — Pydantic BaseSettings
===========================
LexAgent's entire configuration lives in one class: `LexConfig` in lexagent/config.py.
It extends `pydantic_settings.BaseSettings`.

After this file you will understand:
  - What Pydantic is and why it exists
  - What BaseSettings adds on top of Pydantic
  - How AliasChoices lets one field read from multiple env var names
  - Why every field has a default (so the code works offline without a .env file)
  - How to add a new configuration field to LexAgent yourself

Run this file:
    pip install pydantic pydantic-settings
    python 04_pydantic_settings.py
"""

# ──────────────────────────────────────────────
# SECTION 1: What is Pydantic?
# ──────────────────────────────────────────────
# Pydantic is a library that validates data against a schema you define.
# You define a class, declare fields with types, and Pydantic:
#   - Coerces values to the right type (e.g., "42" → 42 for an int field)
#   - Raises a clear ValidationError if a required field is missing or wrong type
#   - Generates .dict(), .json(), and comparison methods for free
#
# Think of it as TypedDict + validation + automatic type coercion.

from pydantic import BaseModel

class MatterBrief(BaseModel):
    matter_id: str
    matter_type: str
    court: str
    year: int = 2024           # default value — optional to provide

# Valid usage:
brief = MatterBrief(matter_id="M-001", matter_type="writ petition", court="Delhi HC")
print("=== SECTION 1: Pydantic BaseModel ===")
print(brief)
print(f"year (defaulted): {brief.year}")

# Pydantic coerces types:
brief2 = MatterBrief(matter_id="M-002", matter_type="injunction", court="Bombay HC", year="2023")
print(f"year as int: {brief2.year} (was passed as string '2023')")


# ──────────────────────────────────────────────
# SECTION 2: What does BaseSettings add?
# ──────────────────────────────────────────────
# BaseSettings (from pydantic_settings) extends BaseModel with one superpower:
# it automatically reads field values from ENVIRONMENT VARIABLES.
#
# So if your class has a field named `anthropic_api_key`,
# BaseSettings will look for an env var called ANTHROPIC_API_KEY automatically.
#
# This is why LexAgent has no manual os.getenv() calls for its config.
# Just define the field in LexConfig and the value appears from .env.

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings

class MinimalConfig(BaseSettings):
    """A simplified version of LexConfig to understand the pattern."""

    # If ANTHROPIC_API_KEY is set in env, it goes here.
    # If not, it's None (the default).
    anthropic_api_key: Optional[str] = None

    # Default model — can be overridden by setting LEX_MODEL in .env
    # Field() wraps the default AND lets us set extra metadata.
    default_model: str = Field("claude-sonnet-4-6")

    # Number of search results from Indian Kanoon (default 3)
    kanoon_max_results: int = Field(3)

    # Where to store matters (default is ~/.lexagent/matters)
    matters_dir: str = Field("~/.lexagent/matters")

    model_config = {
        "env_file": ".env",           # read from .env file in current directory
        "env_file_encoding": "utf-8",
        "extra": "ignore",            # ignore any .env vars not declared here
    }

cfg = MinimalConfig()
print("\n=== SECTION 2: BaseSettings ===")
print(f"default_model: {cfg.default_model}")
print(f"kanoon_max_results: {cfg.kanoon_max_results}")
print(f"anthropic_api_key: {'SET' if cfg.anthropic_api_key else 'NOT SET'}")
print(f"matters_dir: {cfg.matters_dir}")


# ──────────────────────────────────────────────
# SECTION 3: AliasChoices — reading from multiple env var names
# ──────────────────────────────────────────────
# LexAgent supports two naming conventions for every field:
#   1. LEX_prefixed (documented style): LEX_MODEL, LEX_KANOON_MAX_RESULTS
#   2. The bare name: default_model, kanoon_max_results
#
# This makes LexAgent work out of the box if you have ANTHROPIC_API_KEY set
# (which many developers already have), AND with the documented LEX_ prefix.
#
# AliasChoices(choice1, choice2) says "try these env var names in order".

from pydantic import AliasChoices

class LexConfigWithAliases(BaseSettings):
    # This field can be set by EITHER:
    #   ANTHROPIC_API_KEY=sk-ant-...    (bare name — very common)
    #   anthropic_api_key=sk-ant-...    (lowercase — pydantic default)
    anthropic_api_key: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key")
    )

    # This field can be set by EITHER:
    #   LEX_MODEL=claude-opus-4-8       (documented style)
    #   default_model=claude-opus-4-8   (bare name)
    default_model: str = Field(
        "claude-sonnet-4-6",
        validation_alias=AliasChoices("LEX_MODEL", "default_model")
    )

    # This field can be set by EITHER:
    #   LEX_KANOON_MAX_RESULTS=5
    #   kanoon_max_results=5
    kanoon_max_results: int = Field(
        3,
        validation_alias=AliasChoices("LEX_KANOON_MAX_RESULTS", "kanoon_max_results")
    )

    model_config = {"env_file": ".env", "extra": "ignore"}

cfg2 = LexConfigWithAliases()
print("\n=== SECTION 3: AliasChoices ===")
print(f"default_model: {cfg2.default_model}")
print(f"kanoon_max_results: {cfg2.kanoon_max_results}")


# ──────────────────────────────────────────────
# SECTION 4: Feature flags — on/off switches
# ──────────────────────────────────────────────
# LexAgent's advanced features are OFF by default.
# A lawyer enables them by setting env vars in their .env file.
# This means the code works offline with zero config,
# and advanced features activate only when explicitly configured.

class FeatureFlagConfig(BaseSettings):
    # RAGFlow features — all off by default
    raptor_enabled: bool = Field(False, validation_alias=AliasChoices("LEX_RAPTOR_ENABLED", "raptor_enabled"))
    graphrag_enabled: bool = Field(False, validation_alias=AliasChoices("LEX_GRAPHRAG_ENABLED", "graphrag_enabled"))
    reranker_enabled: bool = Field(False, validation_alias=AliasChoices("LEX_RERANKER_ENABLED", "reranker_enabled"))

    # Tool toggles
    tavily_enabled: bool = Field(False, validation_alias=AliasChoices("LEX_TAVILY_ENABLED", "tavily_enabled"))

    model_config = {"env_file": ".env", "extra": "ignore"}

fcfg = FeatureFlagConfig()
print("\n=== SECTION 4: Feature flags ===")
print(f"raptor_enabled: {fcfg.raptor_enabled}")     # False — off by default
print(f"tavily_enabled: {fcfg.tavily_enabled}")     # False — off by default
print("To enable: add LEX_RAPTOR_ENABLED=true to your .env file")


# ──────────────────────────────────────────────
# SECTION 5: List fields — TELEGRAM_ALLOWED_USERS
# ──────────────────────────────────────────────
# LexConfig has one list field: telegram_allowed_users.
# Pydantic Settings can parse a JSON-encoded list from the env var.
# In .env: TELEGRAM_ALLOWED_USERS=[123456789,987654321]

from typing import List

class GatewayConfig(BaseSettings):
    telegram_bot_token: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "telegram_bot_token")
    )
    # default_factory=list creates a new empty list for each instance
    telegram_allowed_users: List[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices("TELEGRAM_ALLOWED_USERS", "telegram_allowed_users")
    )
    model_config = {"env_file": ".env", "extra": "ignore"}

gcfg = GatewayConfig()
print("\n=== SECTION 5: List fields ===")
print(f"telegram_allowed_users: {gcfg.telegram_allowed_users}")  # [] — none configured


# ──────────────────────────────────────────────
# SECTION 6: How to add a new field to LexConfig
# ──────────────────────────────────────────────
# When you need a new configuration option in LexAgent, the pattern is always:
#
# 1. Open lexagent/config.py
# 2. Add a field to LexConfig with a sensible default
# 3. Use AliasChoices with both LEX_prefixed and bare names
# 4. Document what the field does with a WHY comment
#
# Example: adding a "max_draft_length" field:

print("\n=== SECTION 6: Adding a new config field ===")
print("""
# In lexagent/config.py, inside LexConfig class:

# WHY: Prevents runaway LLM output — some models occasionally generate
# multi-thousand-word documents that overwhelm client displays.
max_draft_length: int = Field(
    5000,
    validation_alias=AliasChoices("LEX_MAX_DRAFT_LENGTH", "max_draft_length")
)

# Then in lexagent/nodes/draft.py, after generating the draft:
if len(draft) > cfg.max_draft_length:
    draft = draft[:cfg.max_draft_length] + "\\n\\n[Draft truncated — increase LEX_MAX_DRAFT_LENGTH]"
""")


# ──────────────────────────────────────────────
# PAUSE AND THINK
# ──────────────────────────────────────────────
# Before moving to 05_env_files.py:
#
# 1. What is the difference between Pydantic BaseModel and BaseSettings?
# 2. What does AliasChoices do? Give an example from LexConfig.
# 3. Why do all fields in LexConfig have defaults?
# 4. How would you add a new feature flag "enable_citation_grounding" to LexConfig?
# 5. Open lexagent/config.py and find the field that controls the Kanoon headless mode.
#    What is its default value and why?
#
# When you can answer all five, move on.

print("\n=== DONE — move on to 05_env_files.py ===")
