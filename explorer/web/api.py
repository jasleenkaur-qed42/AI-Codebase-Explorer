from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from explorer import queries, store, trackers
from explorer.web.events import EventBus
from explorer.web.schemas import SessionExplain

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def create_app(repo_path: str) -> FastAPI:
    app = FastAPI(title="AI Codebase Explorer")
    app.state.repo_path = repo_path
    app.state.events = EventBus()

    def _conn():
        return store.connect(store.db_path(repo_path))

    @app.get("/api/repo/stats")
    def repo_stats():
        return queries.repo_stats(_conn())

    @app.get("/api/node")
    def node(id: str):
        detail = queries.node_detail(_conn(), id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"node not found: {id}")
        return detail

    @app.get("/api/graph")
    def graph(node_id: str, depth: int = 1, edge_types: str | None = None, direction: str = "both"):
        types = edge_types.split(",") if edge_types else None
        return queries.graph_around(_conn(), node_id, depth=depth, edge_types=types, direction=direction)

    @app.get("/api/graph/overview")
    def graph_overview(seed_limit: int = 15, depth: int = 1, edge_types: str | None = None):
        types = edge_types.split(",") if edge_types else None
        return queries.graph_overview(_conn(), seed_limit=seed_limit, depth=depth, edge_types=types)

    @app.get("/api/graph/session")
    def graph_session(node_ids: str = "", supporting_ids: str = ""):
        citations = [{"id": n, "role": "primary"} for n in node_ids.split(",") if n]
        citations += [{"id": n, "role": "supporting"} for n in supporting_ids.split(",") if n]
        return queries.session_graph(_conn(), citations)

    @app.get("/api/repo/remote")
    def repo_remote():
        owner_repo = trackers.github_owner_repo(app.state.repo_path)
        if owner_repo is None:
            return {"github_base": None}
        owner, repo = owner_repo
        return {"github_base": f"https://github.com/{owner}/{repo}"}

    @app.get("/api/search")
    def search(table: str, q: str, limit: int = 20):
        return queries.search(_conn(), table, q, limit=limit)

    @app.get("/api/search/symbols")
    def search_symbols(q: str, limit: int = 20):
        return queries.search_nodes(_conn(), q, limit=limit)

    @app.get("/api/path")
    def path(
        from_id: str = Query(alias="from"),
        to_id: str = Query(alias="to"),
        edge_types: str | None = None,
    ):
        types = edge_types.split(",") if edge_types else None
        result = queries.shortest_path(_conn(), from_id, to_id, edge_types=types)
        if result is None:
            raise HTTPException(status_code=404, detail=f"no path between {from_id} and {to_id}")
        return result

    @app.post("/api/session/explain")
    def session_explain(payload: SessionExplain):
        return app.state.events.publish(payload.model_dump())

    @app.get("/api/session/stream")
    def session_stream():
        queue = app.state.events.subscribe()
        return StreamingResponse(app.state.events.stream(queue), media_type="text/event-stream")

    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

    return app
