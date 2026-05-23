# Memory layer for LexAgent.
# Three storage types:
#   soul.py         — ~/.lexagent/SOUL.md (lawyer identity, persists forever)
#   matter_memory.py — ~/.lexagent/matters/{id}/MEMORY.md (per-matter notes)
#   session_store.py — ~/.lexagent/sessions.db (SQLite with FTS5, session history)
