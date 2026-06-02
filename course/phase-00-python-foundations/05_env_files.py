"""
05 — Environment Variables and .env Files
==========================================
LexAgent never hardcodes API keys or paths. They live in .env.
This file explains why, how it works, and what the rules are.

Run this file:
    pip install python-dotenv
    python 05_env_files.py
"""

import os
from pathlib import Path

# ──────────────────────────────────────────────
# SECTION 1: What are environment variables?
# ──────────────────────────────────────────────
# Every process on your computer has a set of key=value pairs
# called environment variables. They are set by the shell before
# the process starts, and the process can read them at any time.
#
# In your terminal:
#   export ANTHROPIC_API_KEY="sk-ant-..."   # set it
#   echo $ANTHROPIC_API_KEY                 # read it
#   unset ANTHROPIC_API_KEY                 # delete it
#
# In Python:
#   os.environ["ANTHROPIC_API_KEY"]         # read it (KeyError if missing)
#   os.environ.get("ANTHROPIC_API_KEY")     # read it (None if missing)
#   os.environ.get("ANTHROPIC_API_KEY", "default")  # with fallback

print("=== SECTION 1: Environment variables ===")
path = os.environ.get("PATH", "not set")
print(f"PATH (first 60 chars): {path[:60]}...")

# The HOME or USERPROFILE env var tells you where the home directory is:
home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "unknown")
print(f"HOME: {home}")

# The ANTHROPIC_API_KEY — probably not set yet on your machine:
api_key = os.environ.get("ANTHROPIC_API_KEY")
print(f"ANTHROPIC_API_KEY: {'SET' if api_key else 'NOT SET (expected for this exercise)'}")


# ──────────────────────────────────────────────
# SECTION 2: Why not hardcode secrets?
# ──────────────────────────────────────────────
# The ONE rule of secrets management: NEVER put secrets in source code.
#
# Why? Because source code gets:
#   - Committed to git repositories
#   - Shared with teammates
#   - Pushed to GitHub (sometimes public by mistake)
#   - Copied into logs and error messages
#
# An API key hardcoded in code is a key waiting to be stolen.
# An API key in an environment variable stays on YOUR machine only.

# BAD — never do this:
# anthropic_api_key = "sk-ant-api03-abc123..."   # DO NOT DO THIS

# GOOD — read from environment:
anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

print("\n=== SECTION 2: Secret hygiene ===")
print("Rule: secrets in environment, never in code")
print(f"API key from env: {'present' if anthropic_api_key else 'absent (correct for a fresh machine)'}")


# ──────────────────────────────────────────────
# SECTION 3: .env files — the convenient middle ground
# ──────────────────────────────────────────────
# Setting env vars manually in your terminal works but is tedious.
# The .env file is a text file where you list your secrets:
#
#   ANTHROPIC_API_KEY=sk-ant-...
#   TELEGRAM_BOT_TOKEN=8123456789:AAF...
#   LEX_MODEL=claude-sonnet-4-6
#
# python-dotenv reads this file and loads it into os.environ.
# pydantic-settings also reads .env automatically if you set env_file=".env".
#
# IMPORTANT: .env is in .gitignore — it never gets committed.
# .env.example IS committed — it shows what variables exist but not their values.

# Manually demonstrating what python-dotenv does:
print("\n=== SECTION 3: .env files ===")

env_content = """
# This is what a .env file looks like. Lines starting with # are comments.
ANTHROPIC_API_KEY=sk-ant-your-key-here
LEX_MODEL=claude-sonnet-4-6
LEX_KANOON_MAX_RESULTS=5
TELEGRAM_BOT_TOKEN=8123456789:AAFxxxxx
LEX_RAPTOR_ENABLED=false
""".strip()

print("A typical LexAgent .env file:")
print(env_content)

# Write it to a temp file and load it:
temp_env = Path("/tmp/lexagent_course_demo.env")
temp_env.write_text(env_content)

# python-dotenv's load_dotenv reads the file and sets os.environ:
from dotenv import load_dotenv
load_dotenv(temp_env, override=False)   # override=False: don't overwrite existing env vars

print(f"\nAfter load_dotenv:")
print(f"  LEX_MODEL: {os.environ.get('LEX_MODEL', 'not set')}")
print(f"  LEX_KANOON_MAX_RESULTS: {os.environ.get('LEX_KANOON_MAX_RESULTS', 'not set')}")
temp_env.unlink()   # clean up


# ──────────────────────────────────────────────
# SECTION 4: The .env file hierarchy in LexAgent
# ──────────────────────────────────────────────
# LexAgent supports multiple levels of configuration:
#
#   1. Built-in defaults     → LexConfig field defaults (e.g., kanoon_max_results=3)
#   2. .env file             → project-level config, in .gitignore
#   3. Environment variables → set in shell, override .env
#   4. Direct field override → cfg = LexConfig(kanoon_max_results=10) in tests
#
# Priority (highest wins): env vars > .env file > LexConfig defaults

print("\n=== SECTION 4: Configuration priority ===")
print("""
Priority (highest wins):
  4. Shell env vars    → export LEX_MODEL=claude-opus-4-8
  3. .env file         → LEX_MODEL=claude-sonnet-4-6
  2. Code defaults     → default_model: str = Field("claude-sonnet-4-6")
  1. Test overrides    → LexConfig(default_model="stub-model")
""")


# ──────────────────────────────────────────────
# SECTION 5: Creating your LexAgent .env file
# ──────────────────────────────────────────────
# Let's create the .env file you will need to run LexAgent for real.
# Run this once. Then fill in your actual API keys.

env_template = """# LexAgent Configuration
# Copy this to your LexAgent project root as `.env`
# Fill in your actual keys. Never commit this file.

# ── Required: LLM Provider (pick one) ──
ANTHROPIC_API_KEY=sk-ant-YOUR-KEY-HERE
# OPENAI_API_KEY=sk-YOUR-KEY-HERE
# GOOGLE_API_KEY=YOUR-KEY-HERE

# ── Optional: Override default model ──
# LEX_MODEL=claude-sonnet-4-6

# ── Optional: Indian Kanoon API ──
# KANOON_API_KEY=YOUR-KEY-HERE

# ── Optional: Telegram Gateway ──
# TELEGRAM_BOT_TOKEN=YOUR-BOT-TOKEN
# TELEGRAM_ALLOWED_USERS=[YOUR_TELEGRAM_USER_ID]

# ── Optional: Advanced Features (all off by default) ──
# LEX_RAPTOR_ENABLED=true
# LEX_GRAPHRAG_ENABLED=true
# LEX_RERANKER_ENABLED=true
# LEX_TAVILY_ENABLED=true
# TAVILY_API_KEY=tvly-YOUR-KEY
"""

print("\n=== SECTION 5: Your .env template ===")
print(env_template)
print("To create this file:")
print("  cd /Users/anshoosareen/Lexagent")
print("  cp .env.example .env  # if it exists, or")
print("  # paste the template above into a new .env file")
print("  # fill in your ANTHROPIC_API_KEY")


# ──────────────────────────────────────────────
# SECTION 6: How pydantic-settings reads .env automatically
# ──────────────────────────────────────────────
# When you write `cfg = LexConfig()`, pydantic-settings:
#   1. Reads the .env file specified in model_config["env_file"]
#   2. Tries to match each env var name to a field (using AliasChoices)
#   3. Fills in the field value (coerced to the right type)
#   4. Falls back to the field default if no env var is found
#
# This all happens in __init__ with zero extra code from you.

print("\n=== SECTION 6: How LexConfig reads .env ===")
print("""
# In lexagent/config.py:

class LexConfig(BaseSettings):
    anthropic_api_key: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key")
    )

    model_config = {
        "env_file": ".env",       # ← reads this file automatically
        "env_file_encoding": "utf-8",
        "extra": "ignore",        # ← ignores unknown env vars silently
    }

# When you do:
cfg = LexConfig()

# pydantic-settings does this automatically:
#   1. Reads /Users/anshoosareen/Lexagent/.env
#   2. Finds ANTHROPIC_API_KEY=sk-ant-...
#   3. AliasChoices matches "ANTHROPIC_API_KEY" to the field
#   4. cfg.anthropic_api_key = "sk-ant-..."
""")


# ──────────────────────────────────────────────
# PAUSE AND THINK
# ──────────────────────────────────────────────
# Final check before Phase 1:
#
# 1. What is the difference between os.environ["KEY"] and os.environ.get("KEY")?
# 2. Why is .env in .gitignore but .env.example is committed?
# 3. If ANTHROPIC_API_KEY is set in your shell AND in .env, which wins?
# 4. If you need a new config value for a feature, what is the correct pattern?
# 5. Open lexagent/config.py, find any field, and trace the full path:
#    - What is the env var name?
#    - What is the default value?
#    - What would you add to .env to change it?
#
# When you can answer all five, you are ready for Phase 1.

print("\n=== PHASE 0 COMPLETE — move on to phase-01-langgraph-core ===")
print("You now understand: TypedDict, async/await, Pydantic Settings, .env files")
print("You can now read lexagent/state.py and lexagent/config.py without confusion.")
