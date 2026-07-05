"""
AI/ML Enhancement API Router

API endpoints for natural language queries, anomaly explanations,
capacity planning, and intelligent alert tuning.
"""

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException

from reaper.engine.ml.anomaly_explainer import AnomalyRootCauseAnalyzer
from reaper.engine.ml.alert_optimizer import IntelligentAlertTuner
from reaper.engine.ml.capacity_planner import PredictiveCapacityPlanner
from reaper.engine.ml.natural_language_interface import CostQueryInterface
from reaper.engine.models.resources import (
    AlertFeedback,
    AlertOptimization,
    AnomalyExplanation,
    CapacityPrediction,
    ChatConversation,
    SessionLocal,
)
from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/ml", tags=["AI/ML Enhancements"])

# Check if AI/ML features are enabled
AI_ML_ENABLED = os.getenv("AI_ML_ENABLED", "true").lower() == "true"

# Initialize AI/ML engines
try:
    if AI_ML_ENABLED:
        cost_query_interface = CostQueryInterface()
        anomaly_analyzer = AnomalyRootCauseAnalyzer()
        capacity_planner = PredictiveCapacityPlanner()
        alert_tuner = IntelligentAlertTuner()
        AI_ML_AVAILABLE = True
        logger.info("AI/ML engines initialized successfully")
    else:
        AI_ML_AVAILABLE = False
        logger.info("AI/ML features are disabled via AI_ML_ENABLED environment variable")
except Exception as e:
    logger.error(f"Failed to initialize AI/ML engines: {e}")
    AI_ML_AVAILABLE = False


# Natural Language Cost Query Endpoints


@router.post("/chat/query")
async def process_cost_query(request: dict[str, Any]) -> dict[str, Any]:
    """
    Process natural language cost query.

    Request body:
    {
        "query": "How much did we spend on Azure VMs last month?",
        "session_id": "user-session-123" (optional)
    }
    """
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    query = request.get("query")
    session_id = request.get("session_id", "default")

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    try:
        result = cost_query_interface.process_query(query, session_id)

        # Store conversation in database
        if result.get("success"):
            db = SessionLocal()
            try:
                conversation = ChatConversation(
                    user_id="system",  # Would use authenticated user ID
                    session_id=session_id,
                    query_text=query,
                    intent_classification=result.get("intent"),
                    response_text=result.get("response"),
                    response_data={"query_results": result.get("query_results")},
                    processing_time_seconds=result.get("processing_time"),
                )
                db.add(conversation)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to store conversation: {e}")
                db.rollback()
            finally:
                db.close()

        return result

    except Exception as e:
        logger.error(f"Cost query processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/history/{session_id}")
async def get_conversation_history(session_id: str) -> dict[str, Any]:
    """Get conversation history for a session."""
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    try:
        history = cost_query_interface.get_conversation_history(session_id)
        return {"session_id": session_id, "history": history}

    except Exception as e:
        logger.error(f"Failed to get conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chat/history/{session_id}")
async def clear_conversation_history(session_id: str) -> dict[str, Any]:
    """Clear conversation history for a session."""
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    try:
        cost_query_interface.clear_conversation_history(session_id)
        return {"message": "Conversation history cleared", "session_id": session_id}

    except Exception as e:
        logger.error(f"Failed to clear conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Anomaly Explanation Endpoints


@router.post("/anomaly/explain")
async def explain_anomaly(request: dict[str, Any]) -> dict[str, Any]:
    """
    Analyze and explain a cost anomaly.

    Request body:
    {
        "anomaly_id": "anomaly-123",
        "resource_id": "resource-456",
        "cost_date": "2024-01-15",
        "cost_amount": 150.00,
        "expected_amount": 50.00
    }
    """
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    anomaly_id = request.get("anomaly_id")
    anomaly_data = request

    if not anomaly_id:
        raise HTTPException(status_code=400, detail="anomaly_id is required")

    try:
        result = anomaly_analyzer.analyze_anomaly(anomaly_id, anomaly_data)

        # Store explanation in database
        if "error" not in result:
            db = SessionLocal()
            try:
                explanation = AnomalyExplanation(
                    anomaly_id=anomaly_id,
                    resource_id=request.get("resource_id"),
                    root_cause=result.get("root_cause"),
                    causal_factors=result.get("causal_factors"),
                    explanation_text=result.get("explanation_text"),
                    confidence_score=result.get("confidence_score"),
                    recommendations=result.get("recommendations"),
                )
                db.add(explanation)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to store anomaly explanation: {e}")
                db.rollback()
            finally:
                db.close()

        return result

    except Exception as e:
        logger.error(f"Anomaly explanation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/anomaly/explanations/{anomaly_id}")
async def get_anomaly_explanation(anomaly_id: str) -> dict[str, Any]:
    """Get stored explanation for an anomaly."""
    try:
        db = SessionLocal()
        explanation = (
            db.query(AnomalyExplanation)
            .filter(AnomalyExplanation.anomaly_id == anomaly_id)
            .first()
        )
        db.close()

        if not explanation:
            raise HTTPException(status_code=404, detail="Explanation not found")

        return {
            "anomaly_id": explanation.anomaly_id,
            "resource_id": explanation.resource_id,
            "root_cause": explanation.root_cause,
            "causal_factors": explanation.causal_factors,
            "explanation_text": explanation.explanation_text,
            "confidence_score": explanation.confidence_score,
            "recommendations": explanation.recommendations,
            "analysis_timestamp": explanation.analysis_timestamp.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get anomaly explanation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Capacity Planning Endpoints


@router.post("/capacity/predict")
async def predict_capacity(request: dict[str, Any]) -> dict[str, Any]:
    """
    Predict future capacity needs for a resource.

    Request body:
    {
        "resource_id": "resource-456",
        "horizon": "medium_term"  // "short_term", "medium_term", "long_term"
    }
    """
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    resource_id = request.get("resource_id")
    horizon = request.get("horizon", "medium_term")

    if not resource_id:
        raise HTTPException(status_code=400, detail="resource_id is required")

    try:
        result = capacity_planner.predict_resource_capacity(resource_id, horizon)

        # Store prediction in database
        if "error" not in result:
            db = SessionLocal()
            try:
                forecast_data = result.get("forecasts", {}).get("ensemble", {})
                prediction = CapacityPrediction(
                    resource_id=resource_id,
                    forecast_horizon_days=capacity_planner.forecast_horizons.get(horizon, 30),
                    predicted_cost=sum(forecast_data.get("values", [0])),
                    confidence_interval_lower=result.get("confidence_intervals", {})
                    .get("intervals", [{}])[0]
                    .get("lower", 0)
                    if result.get("confidence_intervals")
                    else None,
                    confidence_interval_upper=result.get("confidence_intervals", {})
                    .get("intervals", [{}])[0]
                    .get("upper", 0)
                    if result.get("confidence_intervals")
                    else None,
                    model_version="ensemble-v1",
                    forecast_data=result.get("forecasts"),
                )
                db.add(prediction)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to store capacity prediction: {e}")
                db.rollback()
            finally:
                db.close()

        return result

    except Exception as e:
        logger.error(f"Capacity prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/capacity/predict/batch")
async def predict_batch_capacity(request: dict[str, Any]) -> dict[str, Any]:
    """
    Predict capacity needs for multiple resources.

    Request body:
    {
        "resource_ids": ["resource-1", "resource-2", "resource-3"],
        "horizon": "medium_term"
    }
    """
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    resource_ids = request.get("resource_ids", [])
    horizon = request.get("horizon", "medium_term")

    if not resource_ids:
        raise HTTPException(status_code=400, detail="resource_ids is required")

    try:
        result = capacity_planner.predict_multi_resource_capacity(resource_ids, horizon)
        return result

    except Exception as e:
        logger.error(f"Batch capacity prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capacity/predictions/{resource_id}")
async def get_capacity_predictions(resource_id: str) -> dict[str, Any]:
    """Get stored capacity predictions for a resource."""
    try:
        db = SessionLocal()
        predictions = (
            db.query(CapacityPrediction)
            .filter(CapacityPrediction.resource_id == resource_id)
            .order_by(CapacityPrediction.created_at.desc())
            .limit(10)
            .all()
        )
        db.close()

        return {
            "resource_id": resource_id,
            "predictions": [
                {
                    "id": p.id,
                    "prediction_date": p.prediction_date.isoformat(),
                    "forecast_horizon_days": p.forecast_horizon_days,
                    "predicted_cost": p.predicted_cost,
                    "confidence_interval_lower": p.confidence_interval_lower,
                    "confidence_interval_upper": p.confidence_interval_upper,
                    "model_version": p.model_version,
                    "forecast_data": p.forecast_data,
                    "created_at": p.created_at.isoformat(),
                }
                for p in predictions
            ],
        }

    except Exception as e:
        logger.error(f"Failed to get capacity predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alert Optimization Endpoints


@router.post("/alert/feedback")
async def record_alert_feedback(request: dict[str, Any]) -> dict[str, Any]:
    """
    Record user feedback on an alert.

    Request body:
    {
        "alert_id": "alert-123",
        "user_id": "user-456",
        "feedback_type": "acknowledge",  // "dismiss", "snooze", "action_taken"
        "feedback_value": 4,  // optional 1-5 rating
        "response_time_seconds": 120,  // optional
        "feedback_text": "Useful alert"  // optional
    }
    """
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    alert_id = request.get("alert_id")
    user_id = request.get("user_id")
    feedback_type = request.get("feedback_type")

    if not alert_id or not user_id or not feedback_type:
        raise HTTPException(status_code=400, detail="alert_id, user_id, and feedback_type are required")

    try:
        result = alert_tuner.record_alert_feedback(
            alert_id=alert_id,
            user_id=user_id,
            feedback_type=feedback_type,
            feedback_value=request.get("feedback_value"),
            response_time_seconds=request.get("response_time_seconds"),
            feedback_text=request.get("feedback_text"),
        )

        # Store feedback in database
        if result.get("success"):
            db = SessionLocal()
            try:
                feedback = AlertFeedback(
                    alert_id=alert_id,
                    user_id=user_id,
                    feedback_type=feedback_type,
                    feedback_value=request.get("feedback_value"),
                    response_time_seconds=request.get("response_time_seconds"),
                    feedback_text=request.get("feedback_text"),
                )
                db.add(feedback)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to store alert feedback: {e}")
                db.rollback()
            finally:
                db.close()

        return result

    except Exception as e:
        logger.error(f"Alert feedback recording failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alert/optimize-thresholds")
async def optimize_alert_thresholds(request: dict[str, Any]) -> dict[str, Any]:
    """
    Optimize alert thresholds based on user behavior.

    Request body:
    {
        "alert_type": "cost_spike",
        "current_threshold": 100.0,
        "user_id": "user-456"  // optional
    }
    """
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    alert_type = request.get("alert_type")
    current_threshold = request.get("current_threshold")
    user_id = request.get("user_id")

    if not alert_type or current_threshold is None:
        raise HTTPException(status_code=400, detail="alert_type and current_threshold are required")

    try:
        result = alert_tuner.optimize_alert_thresholds(alert_type, current_threshold, user_id)

        # Store optimization in database
        if "error" not in result:
            db = SessionLocal()
            try:
                optimization = AlertOptimization(
                    alert_type=alert_type,
                    user_id=user_id,
                    original_threshold=current_threshold,
                    optimized_threshold=result.get("optimized_threshold"),
                    adjustment_percentage=result.get("adjustment_percentage"),
                    user_sensitivity=result.get("user_sensitivity"),
                    historical_quality=result.get("historical_quality"),
                    rationale=result.get("rationale"),
                    confidence=result.get("confidence"),
                )
                db.add(optimization)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to store alert optimization: {e}")
                db.rollback()
            finally:
                db.close()

        return result

    except Exception as e:
        logger.error(f"Alert threshold optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alert/performance")
async def get_alert_performance(days: int = 30) -> dict[str, Any]:
    """Get overall alert performance metrics."""
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    try:
        result = alert_tuner.analyze_alert_performance(days)
        return result

    except Exception as e:
        logger.error(f"Alert performance analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alert/recommendations")
async def get_alert_recommendations(user_id: str = None) -> dict[str, Any]:
    """Get personalized alert recommendations."""
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    try:
        recommendations = alert_tuner.get_alert_recommendations(user_id)
        return {"user_id": user_id, "recommendations": recommendations}

    except Exception as e:
        logger.error(f"Failed to get alert recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alert/quality/{alert_id}")
async def get_alert_quality(alert_id: str) -> dict[str, Any]:
    """Get quality score for a specific alert."""
    if not AI_ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI/ML features not available")

    try:
        quality = alert_tuner.calculate_alert_quality_score(alert_id)
        return quality

    except Exception as e:
        logger.error(f"Failed to get alert quality: {e}")
        raise HTTPException(status_code=500, detail=str(e))