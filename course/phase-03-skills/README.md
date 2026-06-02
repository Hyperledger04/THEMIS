# Phase 3 — Skills: Markdown as Configuration

> **Status: Coming soon.** Complete Phases 0-2 first.

## What you will build

By the end of this phase, your agent will:
- Automatically load a domain-specific instruction set based on the matter type
- Allow lawyers to create new skills in a text editor with no code changes
- Inject skill content into the system prompt so the LLM follows legal structure

## The files you will understand

- `lexagent/skills/loader.py` — `SkillLoader` class, YAML frontmatter parsing
- `lexagent/skills/civil_litigation.md` — a complete skill file
- `lexagent/skills/legal_notice.md` — a simpler skill file
- `lexagent/prompts/base_system.md` — the base system prompt

## Key concepts

- **Markdown-as-config** — non-technical users can extend the system
- **YAML frontmatter** — metadata in Markdown (`---` blocks)
- **Skill selection by keyword** — matching trigger keywords to matter type
- **System prompt architecture** — why base prompt + skill injection keeps prompts cacheable

## Why this matters

Without skills, the LLM writes every document with the same generic structure.
With skills, a writ petition follows the three-tier structure with prayer clauses;
a legal notice follows the format required by the Consumer Protection Act;
a bail application follows criminal procedure.

The lawyer writes a 50-line Markdown file. The agent produces court-ready documents.

## Coming in this phase

1. `01_yaml_frontmatter.py` — parse YAML frontmatter from Markdown files
2. `02_skill_loader.py` — implement the SkillLoader class
3. `03_prompt_injection.py` — how skills get into the system prompt
4. `exercises/ex01_write_a_skill.md` — write a skill for a new matter type
5. `exercises/ex02_build_loader.py` — implement your own skill loader
