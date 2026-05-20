# src/reaper/web/copilot_routes.py
from flask import Blueprint, jsonify, request

from reaper.engine.copilot_engine import KnapsackCopilotEngine

copilot_api = Blueprint("copilot_api", __name__)
engine_instance = None


def get_engine():
    global engine_instance
    if engine_instance is None:
        engine_instance = KnapsackCopilotEngine()
    return engine_instance


@copilot_api.route("/api/v1/copilot/optimize", methods=["POST"])
def process_optimization_request():
    payload = request.get_json() or {}
    provider = payload.get("provider", "azure").strip().lower()
    user_intent = payload.get("intent", "").strip()
    budget_limit = payload.get("budget_cap")

    if not user_intent or budget_limit is None:
        return jsonify(
            {"status": "error", "message": "Missing mandatory params: 'intent' and 'budget_cap'."}
        ), 400

    try:
        budget_float = float(budget_limit)
        engine = get_engine()
        optimized_result = engine.compile_max_performance_infrastructure(
            cloud_provider=provider, user_intent=user_intent, budget_limit=budget_float
        )
        return jsonify({"status": "success", "blueprint": optimized_result.model_dump()}), 200

    except ValueError:
        return jsonify(
            {
                "status": "error",
                "message": "Invalid type constraint: 'budget_cap' must be a numeric value.",
            }
        ), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Pipeline Execution Fault: {e!s}"}), 500
