"""
Exercise 02 — Build a Simplified LexConfig
===========================================
Your task: write a Pydantic BaseSettings class called `AgentConfig` from scratch.

Requirements:
  - Must read from a .env file
  - Must have at least 5 fields with sensible defaults
  - At least 2 fields must use AliasChoices with LEX_ prefix
  - At least 1 field must be a feature flag (bool, default False)
  - At least 1 field must be Optional[str] for an API key
  - When you run `AgentConfig()`, it must not crash even with no .env file

After defining it, print all field values and their current sources
(from .env, from env var, or from default).

pip install pydantic pydantic-settings
python ex02_build_config.py
"""

from typing import Optional
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings

# ──────────────────────────────────────────────
# YOUR TASK: Define AgentConfig below
# ──────────────────────────────────────────────
class AgentConfig(BaseSettings):
   anthropic_api_key : Optional[str] = Field(default=None, validation_alias= AliasChoices("lex_api_key", "LEX_API_KEY"))
   model_name : Optional[str] = Field(default=None, validation_alias=AliasChoices("Lex_model", "LEX_MODEL"))
   model_provider : Optional[str] = Field("LiteLLM", validation_alias=AliasChoices("anthropic", "ANTHROPIC", "OpenAI", "OLLAMA"))
   kanoon_api : Optional[str] = Field("stub", validation_alias=AliasChoices("KANOON_API", "Kanoon_api", "Indian_Kanoon_api"))
   enable_advanced_research : bool = Field(default=False, validation_alias=AliasChoices("ENABLE_ADVANCED_RESEARCH", "enable_advanced_research"))

   model_config = {"env_file" : ".env", "extra" : "ignore"}
   cfg = AgentConfig()
   print(f"anthropic_api_key: {cfg.anthropic_api_key} (source: {cfg.__fields__['anthropic_api_key'].field_info.extra.get('env_source', 'default')})")

   
# class AgentConfig(BaseSettings):
#     ...    ← fill this in
#
#     model_config = {"env_file": ".env", "extra": "ignore"}

# ──────────────────────────────────────────────
# YOUR TASK: Instantiate and print
# ──────────────────────────────────────────────

# cfg = AgentConfig()
# print("AgentConfig loaded:")
# print(f"  api_key: {'SET' if cfg.??? else 'NOT SET'}")
# ... etc

# ──────────────────────────────────────────────
# BONUS: Test that environment variables override defaults
# ──────────────────────────────────────────────
# import os
# os.environ["LEX_YOUR_FLAG"] = "true"
# cfg2 = AgentConfig()
# print(f"After setting env var: {cfg2.your_flag}")

# ──────────────────────────────────────────────
# REFLECTION (fill in after completing)
# ──────────────────────────────────────────────
# 1. What happens if you remove model_config entirely?
# 2. What is the difference between Field(None) and Field(default_factory=list)?
# 3. If a user sets both ANTHROPIC_API_KEY and anthropic_api_key in their .env,
#    which one wins? (Hint: test it)
