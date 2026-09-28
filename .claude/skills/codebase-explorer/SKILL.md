---
name: codebase-explorer
description: Use when asked anything about a specific repository's code or history — how something is implemented/done, what a function/file/module does, why code exists, what depends on it, how it evolved, who owns it, or what's risky. Resolves the target repo to a local clone (cloning it if needed), ingests it into the `explorer` knowledge graph if that hasn't happened yet, then queries the graph (code structure + git history + docs). Always invoke this for repo questions — never answer from memory, a remote fetch, or grepping instead.
---

# Codebase Explorer

This project's `explorer` CLI parses a repo's code structure and git history
into a SQLite knowledge graph (`.explorer/graph.db` inside the target repo),
then exposes it via `explorer query` subcommands. Use those commands as
tools to answer conversational questions about a repo — don't try to answer
from memory, from a raw GitHub/API fetch, or by grepping alone.

## Step 0: resolve the repo to a local path

Every question here is "about a repo" — resolve it to a local directory
before doing anything else, even if the user only gave a GitHub URL or a
bare repo name:

1. **A local path was given** — use it as-is.
2. **A GitHub URL or `owner/repo` name was given** — first check whether a
   local clone already exists (e.g. `find ~ -maxdepth 4 -iname '<repo-name>'
   -type d 2>/dev/null`, and check any path the user has mentioned in this
   conversation). If found, use that path.
3. **No local clone exists** — clone it yourself before proceeding, e.g. into
   `~/repos/<owner>-<repo-name>` (create the parent dir if needed). Tell the
   user where you cloned it. Do not ask the user to do the cloning — do it,
   then continue.

Only once you have a real local directory do you move to Step 1.

## Step 1: ingest, but only if there's no graph yet

Check for `<repo-path>/.explorer/graph.db`:

- **It exists** — prioritize it. Query straight away; do not re-ingest just
  because a question came in (ingest is incremental/idempotent, but re-running
  it on every question wastes time for no benefit when the graph is already
  there).
- **It doesn't exist** — ingest first, before answering anything:

  ```
  .venv/bin/python3 -m explorer.cli ingest <repo-path>
  ```

  (Or `explorer ingest <repo-path>` if installed as a console script.) Wait
  for it to finish, then proceed to query normally. Never give an answer
  synthesized from browsing/memory instead of the graph just because ingest
  hadn't happened yet — ingest is part of answering the question, not an
  optional setup step the user has to remember to run first.

## Available queries

All commands take `<repo-path>` as the first argument and print JSON.

- `query callers <repo-path> <function-node-id> [--max-depth N]` — who calls this function (direct + transitive, up to N hops)
- `query callees <repo-path> <function-node-id> [--max-depth N]` — what this function calls
- `query churn-hotspots <repo-path> [--top N]` — files ranked by commit churn (most-changed first)
- `query bus-factor-risk <repo-path> [--top N]` — files ranked by risk: low bus factor (few authors) + high churn first — these are the ones where losing one person hurts most
- `query co-change <repo-path> <file-node-id>` — files that tend to change together with this one (hidden coupling)
- `query authors <repo-path> <file-node-id>` — distinct authors who've modified this file
- `query imports <repo-path> <module-node-id>` — what this module/file imports, resolved to the actual local module/file node when the import target lives in the repo (e.g. a relative import or a tsconfig path alias); imports of external packages (react, lodash, etc.) are reported as an `external:<specifier>` placeholder since they aren't part of the repo
- `query search <repo-path> <table> <text>` — full-text search; `table` is one of `docstrings`, `commit_messages`, `docs` (README/docs content), `trackers` (linked GitHub PR/issue titles + descriptions and Jira ticket summaries + descriptions)
- `query commit-for-ref <repo-path> <tracker-node-id>` — given a `pr`/`issue`/`ticket` node id, returns the commit(s) that reference it (hash, message, timestamp) — this is how you answer "which commit implemented X" or "when did PR/ticket Y get merged/committed" once you've found the tracker node via `search trackers`
- `stats <repo-path>` — quick summary: node/edge/commit counts and top churn files

Node IDs look like `function:<path>:<name>:<line>`, `class:<path>:<name>:<line>`,
`file:<path>`, `module:<path>`, `commit:<hash>`, `author:<email>`, `doc:<path>`,
`pr:<owner>/<repo>:<number>`, `issue:<owner>/<repo>:<number>`, `ticket:<JIRA-KEY>`.
Find them via `search` or `churn-hotspots`/`bus-factor-risk` first if you
don't already know the exact ID.

## Issue-tracker linking (GitHub/Jira)

At ingest time, `explorer` scans each mined commit message for GitHub PR
references (`Merge pull request #N`, `... (#N)`, `fixes #N`/`closes #N`, bare
`#N`) and Jira-style ticket keys (`PROJ-123`), then fetches the real PR/issue/
ticket data from the GitHub and Jira REST APIs and links it into the graph
(`references` edges from `commit:<hash>` to the `pr`/`issue`/`ticket` node,
plus full-text indexing under the `trackers` table). This only runs when the
right credentials are configured: `GITHUB_TOKEN` for GitHub (the repo must
also have a `github.com` remote — used to infer owner/repo automatically),
and `JIRA_BASE_URL`/`JIRA_EMAIL`/`JIRA_API_TOKEN` (all three) for Jira. These
are read from real environment variables first, falling back to the `.env`
file at this project's root (`explorer/config.py`) — nothing needs to be
passed on the command line.

If none of these are configured, tracker linking is silently skipped and only
`commit_messages` full-text search is available — mention this to the user
if a tracker-based question comes up empty and no `pr`/`issue`/`ticket` nodes
exist yet.

### Security: credentials are never visible to Claude, and linking is read-only

- **Never read, print, cat, or otherwise display `.env`** (or ask the user to
  paste its contents). It holds the real GitHub/Jira tokens once configured.
  `.claude/settings.json` enforces this by denying `Read`/`cat` on `.env`,
  but treat it as a hard rule regardless: this Skill only ever needs the
  *results* of tracker linking (the `pr`/`issue`/`ticket` nodes already in the
  graph), never the credentials themselves.
- **This project must never write to GitHub or Jira** — no comments, no
  issue/PR edits, no status transitions, nothing. `explorer/trackers.py` is
  read-only by construction (GET requests only, enforced by
  `test_trackers_module_never_issues_write_http_requests`); do not add or
  suggest adding any write capability to it.

## Composing answers

Typical question patterns and how to answer them:

- **"How is X done/implemented? / How does X work?"** → `search docstrings <name>`
  to find the relevant function(s) and their docstrings, then `callees` on the
  entry-point function to trace the implementation flow step by step (each
  callee is a step in the process). Cross-check with `search docs <name>` in
  case the README/docs describe the flow at a higher level. Answer as a
  numbered flow citing file:line for each step.
- **"Which commit implemented X? / When did the PR/ticket for X merge?"** →
  `search trackers <X>` to find the matching `pr`/`issue`/`ticket` node, then
  `commit-for-ref` on its node id to get the implementing commit(s) and their
  timestamps; read `merged_at`/`closed_at`/`state` off the tracker node itself
  for the authoritative merge/close time. Fall back to `search commit_messages`
  if no tracker nodes exist (linking wasn't configured for this repo).
- **"List tickets/PRs related to X"** → `search trackers <X>`, filtering
  results by node `type` (`ticket` for Jira, `pr`/`issue` for GitHub).
- **"Why does X exist / what is X for?"** → `search docstrings <name>` and/or
  `search commit_messages <name>` to find the introducing commit and its
  message; check `docs`/README search too. Cite the commit hash and message.
- **"What depends on X?"** → `callers` for functions; for files/modules, use
  `imports` to see what they depend on directly (resolved to local files where
  possible), plus `co-change` (soft/implicit coupling).
- **"How risky is it to change X?"** → combine `bus-factor-risk` (or look up
  the file's `churn`/`bus_factor`/`coupling` attrs directly) with `co-change`
  (blast radius) and `authors` (who to loop in for review).
- **"How did X evolve?"** → `search commit_messages` filtered to the
  file/function name, ordered by what the commit messages say; mention
  authorship via `authors`.

Always cite concrete evidence (file:line, commit hash, author) rather than
speculating — every answer should be traceable back to a specific query
result.

## Web UI (auto-started on first question per repo)

`explorer serve <repo-path>` starts a local web UI (graph visualization,
repo stats dashboard, node detail panel) for a repo. This section changes
nothing about *how* you answer questions above — it's about additionally
making sure a web UI is available to show that answer in.

### Ensuring a server is running

Before answering a question about an already-ingested repo (i.e. its
`.explorer/graph.db` exists), check whether `<repo-path>/.explorer/serve.json`
exists (a plain local marker file — not a secret, unlike `.env`, so reading
it is fine).

- **If it exists**, treat it as a *candidate*, not a guarantee — the
  process that wrote it may have died without cleaning up (e.g. a `kill -9`
  or a force-closed terminal skips `atexit` handlers). Read its
  `{"host": ..., "port": ...}`, then do a cheap liveness probe before
  trusting it:

  ```bash
  curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://<host>:<port>/api/session/explain"
  ```

  Any HTTP response code (even an error like 405 for a GET against a
  POST-only route) means the server is actually up — proceed straight to
  "Pushing the answer" below. If the probe times out or fails to connect at
  all, the marker is stale: treat this exactly like the "doesn't exist"
  branch below (ignore the stale marker and start a fresh server), subject
  to the same once-per-repo-per-conversation throttle.
- **If it doesn't exist** (or the liveness probe above just failed), start
  one yourself, once per repo per conversation:

  ```bash
  .venv/bin/python3 -m explorer.cli serve <repo-path> --port 8420
  ```

  Run this as a **background** shell command (don't block on it — it's a
  long-running server, not a one-shot command) and give it a moment to come
  up, then re-check `<repo-path>/.explorer/serve.json`. If it now exists,
  proceed as normal below. If starting it failed (e.g. the port was already
  taken, or some other error) or the marker still doesn't appear after a
  couple of seconds, don't keep retrying on every subsequent question in
  this conversation — just answer in chat as usual for the rest of the
  session, exactly as if no server existed.
- Do this at most once per repo per conversation. If you already tried
  (successfully or not) earlier in this conversation, don't try again —
  either the server is already up, or it already failed and retrying won't
  help.

### Pushing the answer

Once a server is confirmed running for this repo, after you've composed
your normal chat answer to the user's question:

1. While answering, keep a running list of every `explorer query`
   invocation you made this turn, as `{command, args, summary}` — e.g.
   `{"command": "query bus-factor-risk", "args": ["<repo>", "--top", "5"], "summary": "3 files, auth.py riskiest"}`.
   This is just the bookkeeping you're already doing to compose the answer,
   not extra reasoning.
2. POST that, plus the question, your answer, and any node ids you cited,
   to the server so the web UI can display it live. Tag each cited node with
   a `role`:
   - `"primary"` — the node is the actual subject of the answer (the
     function/file/module that implements the thing being asked about). The
     web UI's "Related Commits" section pulls a relevance-filtered slice of
     this node's commit history for these.
   - `"supporting"` — the node is cited only as context (e.g. a config file
     you mentioned in passing, or a README you quoted for one sentence of
     background, not because the question was about the README itself). The
     web UI still shows these nodes but never surfaces their commit history —
     a heavily-churned shared file like README.md would otherwise flood
     "Related Commits" with commits unrelated to the actual topic just
     because it was mentioned once.

   When in doubt: if your answer is *about* implementing/understanding that
   node, it's primary; if you only referenced it in support of explaining
   something else, it's supporting.

   ```bash
   curl -s -X POST "http://<host>:<port>/api/session/explain" \
     -H 'Content-Type: application/json' \
     -d '{
       "question": "<the user'"'"'s question>",
       "answer_markdown": "<your answer, as given to the user>",
       "node_ids": [
         {"id": "<node id central to the answer>", "role": "primary"},
         {"id": "<node id cited only for context>", "role": "supporting"}
       ],
       "tools_invoked": [{"command": "query ...", "args": ["..."], "summary": "..."}]
     }'
   ```

   A bare string in `node_ids` (instead of `{"id", "role"}`) is still
   accepted and treated as `"primary"`, but prefer tagging roles explicitly
   so supporting citations don't pollute "Related Commits".

3. If this `curl` fails (server not actually reachable, stale marker file
   left behind by a crashed process) — ignore the failure and move on. It
   must never block, delay, or change your terminal answer to the user.
