# Phase 8 — UX and Output: Rich, Streaming, .docx

> **Status: Coming soon.** Complete Phases 0-7 first.

## What you will build

By the end of this phase, your agent will:
- Show live spinner animations while nodes run
- Stream draft text character-by-character to the terminal
- Export polished Word documents (`.docx`) with proper heading styles
- Show legal trivia while the user waits (contextual loading messages)

## The files you will understand

- `lexagent/ui/live.py` — `LexAnimator`, `LexProgressPanel`, Rich Live display
- `lexagent/ui/spinner.py` — spinner state management
- `lexagent/tools/docx_writer.py` — `write_docx()`, heading styles, paragraph formatting
- `lexagent/data/loading_messages.yaml` — contextual loading messages
- `lexagent/data/legal_trivia.yaml` — trivia shown during long operations

## Key concepts

**Rich** — terminal rendering library. `Console`, `Panel`, `Table`, `Live`, `Spinner`.
  - `console.print("[bold blue]text[/]")` for colored output
  - `Live(...)` for animations that update in place
  - `Panel(text)` for boxed content

**Streaming tokens** — instead of waiting for the full draft:
```python
def on_token(token: str):
    console.print(token, end="")   # print as it arrives

await call_llm(messages, cfg, stream_cb=on_token)
```

**python-docx** — creates Word documents:
  - `Document()` creates a new doc
  - `doc.add_heading(text, level=1)` for headings
  - `doc.add_paragraph(text)` for body text
  - `doc.add_paragraph(text, style="List Bullet")` for bullets
  - `doc.save(path)` writes the file

**LexAnimator** — LexAgent's custom animation system. Shows different messages
("Searching Indian Kanoon...", "Verifying citations...") for each node.
Messages come from `loading_messages.yaml` — no code changes needed to add new ones.

## Coming in this phase

1. `01_rich_basics.py` — Console, Panel, Table, Spinner
2. `02_rich_live.py` — Live display, streaming updates
3. `03_streaming_llm.py` — token streaming from LiteLLM
4. `04_docx_writer.py` — python-docx from first principles
5. `05_loading_messages.py` — YAML-driven contextual messages
6. `exercises/ex01_add_spinner.py` — add a spinner to your graph from Phase 1
7. `exercises/ex02_export_docx.py` — export your draft as a Word document
