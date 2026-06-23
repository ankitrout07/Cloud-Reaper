from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

search_router = APIRouter()

# Initialize search engine only if GEMINI_API_KEY is configured
search_engine = None
try:
    from reaper.rag import DocSearchEngine

    if os.getenv("GEMINI_API_KEY"):
        search_engine = DocSearchEngine()

        # Find project root relative to this file
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        docs_dir_path = base_dir / "docs"

        # Pre-load and index the markdown files into memory on server initialization
        try:
            if docs_dir_path.exists():
                search_engine.load_and_index_docs(docs_dir=str(docs_dir_path))
            else:
                search_engine.load_and_index_docs(docs_dir="docs")
        except Exception as e:
            print(f"WARN: Initial documentation indexing bypassed: {e!s}")
    else:
        print("WARN: GEMINI_API_KEY not configured, search functionality disabled")
except Exception as e:
    print(f"WARN: Search engine initialization failed: {e!s}")


@search_router.post("/api/v1/docs/search")
async def handle_docs_search(payload: dict[str, Any] | None = None):
    payload = payload or {}
    query_string = payload.get("query", "").strip()

    if not query_string:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Search query string parameter cannot be blank.",
            },
        )

    if search_engine is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "Search functionality is not available. GEMINI_API_KEY not configured.",
            },
        )

    try:
        search_hits = search_engine.query_docs(user_query=query_string, top_k=3)
        return {"status": "success", "results": search_hits}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Documentation engine fault: {e!s}"},
        )
