# Runtime Flow Map

**Source:** CRG flow analysis (30 flows, sorted by criticality) + direct inspection

---

## Primary Production Flows

### Flow 1: CLI Draft (`lex draft "matter brief"`)
Criticality: ~0.62 (via `_run_draft`)

```
CLI (cli.py::_run_draft)
  → LexConfig()                         [reads .env]
  → get_graph()                          [compiles or returns cached graph]
  → graph.astream(initial_state, config) [LangGraph invocation]
      → intake.run(state)
          → SOUL.md load (memory/soul.py)
          → skill selection (skills/loader.py)
          → LLM: clarifying questions OR intake_complete=True
          → returns partial LexState dict
      → [if intake_complete=False] → END (caller loops and re-invokes)
      → [if intake_complete=True]
          → react_research.run(state) OR retrieve.run(state) [if no-research type]
              → ToolRegistry.get_langchain_tools()
              → LLM with tool_calls bound
              → Kanoon / search / limitation / legal_kg calls
              → returns research_findings, statutes_cited, limitation_analysis
          → retrieve.run(state)
              → BM25 + TF-IDF hybrid search over Qdrant or in-memory index
              → returns retrieval_chunks, grounded_citations
          → draft.run(state)
              → Prompts: soul + skill + research_findings + retrieval_chunks → LLM
              → returns draft_output, plain_english_summary
          → [if auto_verify_citations] → cite.run(state)
              → Extract citations from draft_output
              → Verify each against Kanoon / research corpus
              → returns citations_verified, unverified_citations
          → review.run(state)
              → Word count check, jurisdiction limit check
              → write_docx() if --output requested
              → returns docx_path, risk_annotations
  ← Rich output: draft + citations table + summary
```

**What's missing here:** No workspace write. `LexState` dict carries everything. On completion, matter memory is saved to `~/.lexagent/matters/{id}/MEMORY.md` as append-only markdown.

---

### Flow 2: Telegram (`handle_text`, `handle_callback`, `handle_document`)
Criticality: 0.573–0.578 combined

```
Telegram update
  → telegram.py::handle_text / handle_callback / handle_document
      → _get_or_create_session(user_id)  [SQLite sessions.db]
      → reconstruct LexState from session
      → [handle_callback] → route by callback_data (post-draft actions)
      → [handle_document] → ingest PDF → contract_review or document_qa
      → _run_graph_for_user(state)       [hub: 63 total degree, CRG]
          → get_graph().astream(state)   [same graph as CLI]
          → streaming responses → Telegram Bot API
      → save session back to SQLite
      → send .docx if docx_path set
```

**What's missing:** Session isolation does not enforce `firm_id`. Multiple Telegram users in a multi-tenant deployment can share the same SQLite session store without firm-level partitioning.

---

### Flow 3: Voice WebSocket (highest criticality: 0.728)
```
HTTP Upgrade to WebSocket
  → voice.py::ws_endpoint(websocket)
      → VoiceSession(session_id, channel="websocket")
      → voice.py::voice_websocket(websocket, session)
          → loop: receive audio bytes
          → STT backend (Whisper / Deepgram / stub)
          → text → _run_graph_for_user() [same graph]
          → response text → TTS backend (Google / ElevenLabs / stub)
          → stream audio bytes back
```

**Note:** Voice is the highest-criticality flow by CRG metric but is a tertiary UX channel. This suggests test coupling, not actual production importance.

---

### Flow 4: Contract Draft / Review
Criticality: 0.645–0.655 (top 2 non-voice flows)

```
CLI/Telegram: --mode contract_review / contract_draft
  → build LexState with workflow_mode="contract_review"
  → graph: intake → contract_review → END
      → contract_review.run(state)
          → load contract PDF
          → load playbook (if active_playbook set)
          → LLM: clause map + risk analysis + deviations
          → returns contract_risk_analysis, contract_review_output
```

---

### Flow 5: Runtime Worker (background, not yet connected to graph)
```
lex worker [CLI command]
  → RuntimeWorker(repo, poll_interval=5.0)
  → asyncio poll loop:
      → repo.get_queued_jobs(limit=5)
      → for each job:
          → _HANDLERS.get(job.type)
          → CostLedger + HaltFlag instantiated
          → halt_flag.should_halt() checked
          → await handler(job, repo)
              → [ONLY IMPLEMENTED] handle_process_uploaded_documents:
                  → ingest_file(document_path)
                  → extract_from_pages(pages)  [facts, parties, issues, dates]
                  → build_chronology(anchors)
                  → repo.save_extracted_fact() / save_chronology_item() etc.
              → [NOT IMPLEMENTED] handle_research_memo
              → [NOT IMPLEMENTED] handle_risk_analysis
              → [NOT IMPLEMENTED] handle_morning_brief
              → [NOT IMPLEMENTED] handle_deadline_scan
              → [NOT IMPLEMENTED] handle_next_actions
              → [NOT IMPLEMENTED] handle_draft_next_document
          → repo.update_job_status(job.job_id, "completed")
```

---

## State Lifecycle

```
Matter lifecycle:
  LexState (ephemeral, per graph run)
  ├─ Created: control plane / CLI builds initial dict
  ├─ Lives: in-memory during graph execution
  ├─ Persisted: LangGraph checkpointer (keyed by thread_id)
  └─ After run: appended to MEMORY.md + state.json

PostgresWorkspaceRepository (durable, per matter)
  ├─ Created: [nothing creates it from the graph yet]
  ├─ Lives: Postgres tables
  ├─ Read by: RuntimeWorker (via jobs.py)
  └─ Written by: RuntimeWorker only

The two persistence paths do not communicate.
```

---

## Failure Modes in Current Flow

1. **LexState is the only truth during graph execution** — if the graph crashes mid-run, unsaved intermediate research findings, extracted facts, and drafted authorities are lost. No checkpoint-to-workspace sync.

2. **Workspace writes require the worker** — the graph cannot persist to the workspace. If a lawyer runs `lex draft` and gets a response, that draft is in `MEMORY.md` and `LexState` checkpointer — not in the `drafts` table where it belongs.

3. **Multi-tenant session bleed risk** — Telegram sessions keyed by `user_id` only; `firm_id` not enforced in SQLite session queries. `test_matter_isolation.py` exists and checks Postgres workspace isolation — but not session-level isolation.

4. **Job queue without enqueue path** — `RuntimeWorker` polls jobs from Postgres, but there is no API endpoint or graph node that creates jobs. The `process_uploaded_documents` handler exists; no code calls `repo.enqueue_job()` from the control plane or CLI.
