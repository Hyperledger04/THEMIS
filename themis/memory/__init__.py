# Memory layer for Themis.
# Three storage types:
#   soul.py         — ~/.themis/SOUL.md (lawyer identity, persists forever)
#   matter_memory.py — ~/.themis/matters/{id}/MEMORY.md (per-matter notes)
#   session_store.py — ~/.themis/sessions.db (SQLite with FTS5, session history)
