from pathlib import Path

from flask import Blueprint, jsonify, request

from reaper.rag import DocSearchEngine

search_bp = Blueprint("search_api", __name__)
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


@search_bp.route("/api/v1/docs/search", methods=["POST"])
def handle_docs_search():
    payload = request.get_json() or {}
    query_string = payload.get("query", "").strip()

    if not query_string:
        return jsonify(
            {"status": "error", "message": "Search query string parameter cannot be blank."}
        ), 400

    try:
        search_hits = search_engine.query_docs(user_query=query_string, top_k=3)
        return jsonify({"status": "success", "results": search_hits}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Documentation engine fault: {e!s}"}), 500
