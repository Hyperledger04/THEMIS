# Phase 0 — Python Foundations

Before you can understand LexAgent's code, you need to be comfortable with four Python patterns that appear *everywhere* in the codebase:

1. **Type annotations + TypedDict** — LexAgent's entire state is a TypedDict called `LexState`. If you do not know what that means, the graph code is unreadable.
2. **async / await** — Every node in the graph is an `async def` function. If you have not used async before, the node contract will feel magical (bad magic).
3. **Pydantic BaseSettings** — `LexConfig` is a Pydantic settings class. It reads from `.env` files automatically. You need to understand why, not just that.
4. **Environment variables and .env files** — LexAgent never hardcodes API keys. They live in `.env`. You need to know how that works.

Each file in this phase teaches one of these. Run every file. Read the output. Do the exercises.

---

## Files in this phase

| File | Teaches |
|------|---------|
| `01_python_basics.py` | Variables, functions, modules, the import system |
| `02_type_hints_typeddict.py` | Type annotations and TypedDict — the foundation of LexState |
| `03_async_await.py` | async/await from first principles — the foundation of LexAgent nodes |
| `04_pydantic_settings.py` | Pydantic BaseSettings — the foundation of LexConfig |
| `05_env_files.py` | .env files and why LexAgent uses them |
| `exercises/ex01_build_state.py` | Build a simplified version of LexState yourself |
| `exercises/ex02_build_config.py` | Build a simplified version of LexConfig yourself |

---

## The connection to LexAgent

After this phase you will be able to open `lexagent/state.py` and understand every line. You will also be able to open `lexagent/config.py` and understand why every field is written the way it is.

That is the goal. Let's go.
