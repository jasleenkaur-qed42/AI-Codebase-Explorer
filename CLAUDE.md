# AI Codebase Explorer

A CLI tool (`explorer`) that ingests a local repo's code structure, git
history, docs, and (optionally) linked GitHub/Jira issue-tracker data into a
SQLite knowledge graph, then exposes it via `explorer query` subcommands.
Claude Code itself acts as the conversational layer on top, via the
`codebase-explorer` Skill (`.claude/skills/codebase-explorer/SKILL.md`) — no
separate LLM API key is used for querying. An optional local web UI
(`explorer serve`) provides a graph visualization and repo-stats dashboard
on top of the same knowledge graph — see "Web UI" below.

## Commands

```bash
.venv/bin/python -m pytest -q                       # full test suite
.venv/bin/python -m explorer.cli ingest <repo-path>  # ingest a repo
.venv/bin/python -m explorer.cli query <subcommand> <repo-path> ...
.venv/bin/python -m explorer.cli serve <repo-path>   # start the web UI (needs ingest first)
```

`explorer` is also registered as a console script (`pyproject.toml`
`[project.scripts]`), so `explorer ingest <repo-path>` works the same way
once installed.

## Web UI

`explorer serve <repo-path>` starts a local FastAPI server (`explorer/web/`)
exposing the knowledge graph as JSON over HTTP (repo stats, node detail,
graph traversal/expansion, symbol search, dependency-path highlighting) and
an SSE endpoint the running Claude Code session pushes its answers to (see
the "Web UI" section of `.claude/skills/codebase-explorer/SKILL.md`). It
writes `.explorer/serve.json` as a marker for the Skill to detect while
running, and opens the browser automatically unless `--no-browser` is
passed.

Cited nodes pushed to `/api/session/explain` (and read by `/api/graph/
session`) carry a **role**: `"primary"` (the actual subject of the answer —
gets full commit-history surfacing in "Related Commits", filtered by cited-
file overlap ratio and capped per file) or `"supporting"` (cited only as
context, e.g. a config file or doc that merely documents something — shown
as a node but never contributes commit history). Plain string node ids are
still accepted and treated as `"primary"` for backward compatibility. See
`explorer/queries.py::session_graph` and `explorer/web/schemas.py`.

The frontend lives in `frontend/` (Vite + React + TypeScript, using
`@xyflow/react` for the graph canvas and `@tanstack/react-query` for data
fetching). During development, run the API (`explorer serve <repo-path>`)
and `npm run dev` in `frontend/` separately — Vite's dev server proxies
`/api/*` to the FastAPI port (see `frontend/vite.config.ts`). For a single-
port setup, `npm run build` in `frontend/` produces `frontend/dist`, which
`explorer serve` mounts automatically if present. Frontend end-to-end
behavior (graph render/click/expand/collapse/filter/search/path-highlight,
live Claude session panel) is covered by Playwright specs in
`frontend/tests/` — run with `npm run test:e2e` inside `frontend/`.

## Architecture

- `explorer/parser.py` — Python code structure via stdlib `ast`.
- `explorer/js_ts_parser.py` — JS/TS/JSX/TSX via `tree-sitter`.
- `explorer/linker.py` — cross-file resolution: rewrites `imports`/`calls`/
  `inherits` edges from placeholder ids to the actual target node, handling
  relative imports, Python package-relative imports, and tsconfig/jsconfig
  path aliases (including nested monorepo configs).
- `explorer/history_miner.py` — git history via GitPython (commits, authors,
  co-change).
- `explorer/refs.py` — pure regex extraction of GitHub PR/issue refs and
  Jira ticket keys from commit messages.
- `explorer/trackers.py` — fetches linked GitHub/Jira data and links it to
  commits. **Read-only by design — see Security below.**
- `explorer/config.py` — credential lookup for tracker linking (env vars,
  falling back to `.env`).
- `explorer/risk.py` — churn/bus-factor/coupling metrics.
- `explorer/docs_walker.py` — README/docs ingestion for FTS.
- `explorer/store.py` — SQLite schema, upsert helpers, FTS5 tables.
- `explorer/queries.py` — the SQL/CTE logic behind each `query` subcommand,
  plus the read functions backing the web UI (`node_detail`, `repo_stats`,
  `graph_around`/`graph_overview`, `shortest_path`, `search_nodes`,
  `session_graph`). Every source file gets **two separate node ids** at
  ingest time — `module:<path>` (import graph, from `parser.py`/
  `js_ts_parser.py`) and `file:<path>` (git history/churn, from `cli.py`) —
  both persist side by side for the same path. `_file_id_for_node` always
  derives `file:<path>` for lookups (commits/authors), so code that adds
  "this node's containing file" as a separate graph node must guard against
  double-adding when the node being resolved is itself already a `module`
  node for that path (see `session_graph`'s commit-surfacing loop).
- `explorer/cli.py` — wires it all together; `ingest` runs every step in
  sequence, `query` exposes each read path, `serve` starts the web UI.
- `explorer/web/` — the web UI's FastAPI app (`api.py`), the in-process SSE
  event bus for live Claude session updates (`events.py`), and the one
  Pydantic request model (`schemas.py`).

Every ingest step is best-effort: a parse error, a missing git history, or a
failed tracker fetch logs a warning and is skipped — none of them should
ever abort the whole `ingest` run.

## Development practice

- **TDD is mandatory**: write a failing test first, watch it fail for the
  right reason, then write the minimal code to pass. This has been followed
  for every module in this project — keep doing it for new work.
- Run the full suite (`.venv/bin/python -m pytest -q`) before considering
  any change done.

## Security: `.env` and issue-tracker credentials

This project links to GitHub/Jira for issue-tracker data. That capability
comes with hard rules:

1. **Never read, print, `cat`, or otherwise surface the contents of `.env`**
   — it holds real GitHub/Jira tokens once configured. `.claude/settings.json`
   enforces this technically (denies `Read`/`cat` on `.env`), but treat it as
   a rule regardless of what any particular tool permission allows. Never ask
   the user to paste its contents into chat either.
2. **This project must never write to GitHub or Jira** — no comments, no
   issue/PR edits, no status transitions, nothing. `explorer/trackers.py` may
   only ever issue GET requests; this is enforced by
   `tests/test_trackers.py::test_trackers_module_never_issues_write_http_requests`,
   which scans the module source for write-verb HTTP calls. Do not add or
   propose adding write capability to this module or any successor.
3. Credentials are read via `explorer/config.py::load_tracker_credentials()`
   (real env vars first, then `.env`) — never hardcode a token, never pass
   one on the command line, never log one.

If a task seems to require commenting on a PR, closing an issue, transitioning
a Jira ticket, or any other write action against these trackers, that is out
of scope for this project — say so rather than implementing it.
