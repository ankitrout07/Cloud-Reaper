"""
FinOps Pipeline Scheduler
Enforces sequential optimization operations to prevent capital waste.
Order: Telemetry Collection → Rightsizing → Baseline Update → Commitment Management
"""

import logging
from datetime import UTC, datetime
from typing import Any

import numpy as np

from reaper.engine.core.calculator import RightsizingAgent
from reaper.engine.core.logic import RightSizer
from reaper.engine.core.workload import WorkloadPersonality
from reaper.engine.models.resources import (
    OptimizationBaseline,
    get_db_session,
)

logger = logging.getLogger(__name__)


class WorkloadClassifier:
    """
    Classifies workloads into environment types based on resource tags and naming patterns.
    Enables safe separation of aggressive dev-test automation from production guardrails.
    """

    PRODUCTION_KEYWORDS = ["prod", "production", "live", "main", "master"]
    DEV_TEST_KEYWORDS = ["dev", "test", "staging", "sandbox", "demo", "poc"]

    def __init__(self):
        self.tag_key_mapping = {
            "environment": ["env", "environment", "tier"],
            "workload": ["workload", "app", "application"],
            "cost_center": ["cost-center", "costcenter", "billing"],
        }

    def classify_resource(self, resource: dict[str, Any]) -> str:
        """
        Classifies a resource as 'production' or 'dev-test' based on tags and naming.

        Args:
            resource: Dictionary with 'tags', 'name', and other resource metadata

        Returns:
            'production' or 'dev-test'
        """
        tags = resource.get("tags", {})
        resource_name = resource.get("name", "").lower()

        # Check tags first (most reliable)
        for _tag_key, variations in self.tag_key_mapping.items():
            for variation in variations:
                if variation in tags:
                    env_value = str(tags[variation]).lower()
                    if any(kw in env_value for kw in self.PRODUCTION_KEYWORDS):
                        return "production"
                    if any(kw in env_value for kw in self.DEV_TEST_KEYWORDS):
                        return "dev-test"

        # Fallback to name-based classification
        if any(kw in resource_name for kw in self.PRODUCTION_KEYWORDS):
            return "production"
        if any(kw in resource_name for kw in self.DEV_TEST_KEYWORDS):
            return "dev-test"

        # Default to production for safety (more conservative thresholds)
        return "production"

    def batch_classify(self, resources: list[dict[str, Any]]) -> dict[str, str]:
        """
        Classifies multiple resources and returns a mapping of resource_id to environment type.

        Args:
            resources: List of resource dictionaries

        Returns:
            Dictionary mapping resource IDs to 'production' or 'dev-test'
        """
        classification = {}
        for resource in resources:
            resource_id = resource.get("id", resource.get("name", "unknown"))
            classification[resource_id] = self.classify_resource(resource)
        return classification


class FinOpsPipeline:
    """
    Sequential FinOps pipeline that enforces the correct order of operations:
    1. Telemetry Collection (Go scraper)
    2. Rightsizing (Python Q-learning + vectorized analysis)
    3. Baseline Update (SQLite)
    4. Commitment Management (RI/SP Advisor based on optimized baseline)
    """

    def __init__(self, price_book=None):
        self.price_book = price_book or {}
        self.workload_classifier = WorkloadClassifier()
        self.rightsizing_agent = RightsizingAgent()
        self.right_sizer = RightSizer(price_book=price_book)
        self.workload_analyzer = WorkloadPersonality()

    def execute_pipeline(
        self,
        telemetry_data: list[dict[str, Any]],
        provider: str = "azure",
        lookback_days: int = 7,
    ) -> dict[str, Any]:
        """
        Executes the complete FinOps pipeline in the correct sequence.

        Args:
            telemetry_data: Raw telemetry from Go scraper with resource metrics
            provider: Cloud provider (azure, aws, gcp)
            lookback_days: Number of days to analyze (7, 14, 30)

        Returns:
            Pipeline execution results with rightsizing recommendations and commitment insights
        """
        logger.info(f"Starting FinOps Pipeline for {provider} with {lookback_days}-day lookback")
        pipeline_start = datetime.now(UTC)

        results = {
            "pipeline_status": "in_progress",
            "provider": provider,
            "lookback_days": lookback_days,
            "timestamp": pipeline_start.isoformat(),
            "stages": {},
            "final_recommendations": [],
        }

        try:
            # STAGE 1: Telemetry Collection & Classification
            logger.info("Stage 1: Telemetry Collection & Workload Classification")
            stage1_result = self._stage_telemetry_classification(telemetry_data)
            results["stages"]["telemetry_classification"] = stage1_result

            if not stage1_result["success"]:
                raise Exception("Telemetry classification failed")

            # STAGE 2: Rightsizing Analysis (Q-learning + Vectorized)
            logger.info("Stage 2: Rightsizing Analysis with Q-learning")
            stage2_result = self._stage_rightsizing_analysis(
                stage1_result["classified_resources"],
                stage1_result["environment_mapping"],
                lookback_days,
            )
            results["stages"]["rightsizing_analysis"] = stage2_result

            # STAGE 3: Baseline Update (SQLite persistence)
            logger.info("Stage 3: Optimization Baseline Update")
            stage3_result = self._stage_baseline_update(
                stage2_result["rightsizing_recommendations"], provider
            )
            results["stages"]["baseline_update"] = stage3_result

            # STAGE 4: Commitment Management (Based on OPTIMIZED baseline)
            logger.info("Stage 4: Commitment Management Analysis")
            stage4_result = self._stage_commitment_management(
                stage3_result["optimized_baseline"], provider
            )
            results["stages"]["commitment_management"] = stage4_result

            # Compile final recommendations
            results["final_recommendations"] = stage2_result["rightsizing_recommendations"]
            results["commitment_recommendations"] = stage4_result["commitment_insights"]
            results["pipeline_status"] = "completed"
            results["execution_time_seconds"] = (datetime.now(UTC) - pipeline_start).total_seconds()

            logger.info(f"FinOps Pipeline completed in {results['execution_time_seconds']:.2f}s")
            return results

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            results["pipeline_status"] = "failed"
            results["error"] = str(e)
            results["execution_time_seconds"] = (datetime.now(UTC) - pipeline_start).total_seconds()
            return results

    def _stage_telemetry_classification(
        self, telemetry_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Stage 1: Classify resources by environment type (production vs dev-test).
        This enables different threshold policies for safety.
        """
        try:
            classified_resources = []
            environment_mapping = self.workload_classifier.batch_classify(telemetry_data)

            for resource in telemetry_data:
                resource_id = resource.get("id", resource.get("name", "unknown"))
                env_type = environment_mapping.get(resource_id, "production")
                resource["environment_type"] = env_type
                classified_resources.append(resource)

            production_count = sum(1 for env in environment_mapping.values() if env == "production")
            dev_test_count = len(environment_mapping) - production_count

            return {
                "success": True,
                "classified_resources": classified_resources,
                "environment_mapping": environment_mapping,
                "summary": {
                    "total_resources": len(classified_resources),
                    "production_resources": production_count,
                    "dev_test_resources": dev_test_count,
                },
            }

        except Exception as e:
            logger.error(f"Telemetry classification failed: {e}")
            return {"success": False, "error": str(e)}

    def _stage_rightsizing_analysis(
        self,
        classified_resources: list[dict[str, Any]],
        environment_mapping: dict[str, str],
        lookback_days: int,
    ) -> dict[str, Any]:
        """
        Stage 2: Perform rightsizing analysis using Q-learning agent and vectorized operations.
        Applies environment-aware thresholds for safety.
        """
        try:
            rightsizing_recommendations = []

            for resource in classified_resources:
                resource_id = resource.get("id", resource.get("name", "unknown"))
                env_type = environment_mapping.get(resource_id, "production")

                # Extract usage history for vectorized analysis
                cpu_history = resource.get("cpu_history", [0] * lookback_days)
                memory_history = resource.get("memory_history", [0] * lookback_days)

                # Convert to numpy arrays for vectorized processing
                cpu_matrix = np.array([cpu_history[-lookback_days:]], dtype=np.float64)
                memory_matrix = np.array([memory_history[-lookback_days:]], dtype=np.float64)

                # Perform vectorized compute telemetry analysis
                telemetry_analysis = self._analyze_single_resource_telemetry(
                    cpu_matrix, memory_matrix, env_type=env_type, lookback_days=lookback_days
                )

                # Get workload personality for context
                personality = self.workload_analyzer.analyze(cpu_history)

                # Q-learning agent evaluation
                current_sku = resource.get("sku", "unknown")
                metrics = {
                    "cpu": telemetry_analysis["avg_cpu"],
                    "mem": telemetry_analysis["avg_memory"],
                    "iops": resource.get("iops", 50),
                    "net": resource.get("network_throughput", 40),
                }

                rl_evaluation = self.rightsizing_agent.evaluate_migration(metrics, current_sku)

                # Combine heuristic and RL recommendations
                recommendation = {
                    "resource_id": resource_id,
                    "resource_name": resource.get("name", "unknown"),
                    "current_sku": current_sku,
                    "environment_type": env_type,
                    "telemetry_analysis": telemetry_analysis,
                    "workload_personality": personality,
                    "rl_evaluation": rl_evaluation,
                    "recommended_action": self._determine_final_action(
                        telemetry_analysis, rl_evaluation, env_type
                    ),
                    "confidence": self._calculate_confidence(
                        telemetry_analysis, personality, rl_evaluation
                    ),
                }

                rightsizing_recommendations.append(recommendation)

            return {
                "success": True,
                "rightsizing_recommendations": rightsizing_recommendations,
                "summary": {
                    "total_recommendations": len(rightsizing_recommendations),
                    "shutdown_candidates": sum(
                        1
                        for r in rightsizing_recommendations
                        if r["recommended_action"] == "SHUTDOWN"
                    ),
                    "rightsizing_candidates": sum(
                        1
                        for r in rightsizing_recommendations
                        if "RIGHTSIZE" in r["recommended_action"]
                    ),
                },
            }

        except Exception as e:
            logger.error(f"Rightsizing analysis failed: {e}")
            return {"success": False, "error": str(e)}

    def _analyze_single_resource_telemetry(
        self,
        cpu_matrix: np.ndarray,
        memory_matrix: np.ndarray,
        env_type: str = "production",
        lookback_days: int = 7,
    ) -> dict[str, Any]:
        """
        Vectorized evaluation of compute performance data over variable lookback windows.
        Differentiates thresholds between production and dev-test environments safely.

        Args:
            cpu_matrix: 2D numpy array of CPU usage data (resources x days)
            memory_matrix: 2D numpy array of memory usage data (resources x days)
            env_type: 'production' or 'dev-test' for threshold differentiation
            lookback_days: Number of days to analyze (7, 14, 30)

        Returns:
            Dictionary with analysis results and recommendations
        """
        # Slice the input matrices to target the exact user lookback timeframe
        cpu_slice = cpu_matrix[:, -lookback_days:]
        mem_slice = memory_matrix[:, -lookback_days:]

        # High-velocity vectorized average calculations bypassing the Python GIL
        avg_cpu = float(np.mean(cpu_slice, axis=1)[0]) if cpu_slice.size > 0 else 0.0
        max_cpu = float(np.max(cpu_slice, axis=1)[0]) if cpu_slice.size > 0 else 0.0
        min_cpu = float(np.min(cpu_slice, axis=1)[0]) if cpu_slice.size > 0 else 0.0
        std_cpu = float(np.std(cpu_slice, axis=1)[0]) if cpu_slice.size > 0 else 0.0

        avg_mem = float(np.mean(mem_slice, axis=1)[0]) if mem_slice.size > 0 else 0.0
        max_mem = float(np.max(mem_slice, axis=1)[0]) if mem_slice.size > 0 else 0.0

        # Establish thresholds based on explicit workload differentiation rules
        # Production uses more conservative (lower) thresholds for safety
        cpu_shutdown_threshold = 5.0 if env_type == "production" else 15.0
        cpu_rightsizing_threshold = 20.0 if env_type == "production" else 30.0
        burst_eligible_threshold = 70.0

        # Generate recommendations using vectorized comparisons
        if max_cpu < cpu_shutdown_threshold:
            action = "SHUTDOWN"
            impact = "HIGH"
            reason = "Idle resource threshold breach"
        elif avg_cpu < cpu_rightsizing_threshold and max_cpu > burst_eligible_threshold:
            action = "RIGHTSIZE_BURSTABLE"
            impact = "MEDIUM"
            reason = "Fits burstable B-Series profile"
        elif avg_cpu < cpu_rightsizing_threshold:
            action = "RIGHTSIZE_DOWN"
            impact = "MEDIUM"
            reason = "Consistently low utilization"
        else:
            action = "STAY"
            impact = "LOW"
            reason = "Stable operation baseline"

        return {
            "avg_cpu": avg_cpu,
            "max_cpu": max_cpu,
            "min_cpu": min_cpu,
            "std_cpu": std_cpu,
            "avg_memory": avg_mem,
            "max_memory": max_mem,
            "lookback_days": lookback_days,
            "environment_type": env_type,
            "recommended_action": action,
            "impact": impact,
            "reason": reason,
            "thresholds_used": {
                "cpu_shutdown": cpu_shutdown_threshold,
                "cpu_rightsizing": cpu_rightsizing_threshold,
                "burst_eligible": burst_eligible_threshold,
            },
        }

    def _determine_final_action(
        self, telemetry_analysis: dict, rl_evaluation: dict, env_type: str
    ) -> str:
        """
        Combines heuristic telemetry analysis with RL agent evaluation
        to determine the final recommended action.
        """
        telemetry_action = telemetry_analysis["recommended_action"]
        rl_action = rl_evaluation["recommended_action"]
        risk_profile = rl_evaluation["risk_profile"]

        # Production safety: Override aggressive RL actions with conservative heuristics
        if env_type == "production" and risk_profile == "High":
            return telemetry_action  # Trust heuristic analysis for production safety

        # Dev-test: Allow more aggressive RL recommendations
        if rl_action in ["downscale", "migrate_family"] and risk_profile != "High":
            return f"RIGHTSIZE_{rl_action.upper()}"

        # Default to telemetry analysis
        return telemetry_action

    def _calculate_confidence(
        self, telemetry_analysis: dict, personality: dict, rl_evaluation: dict
    ) -> float:
        """
        Calculates overall confidence score based on multiple factors.
        """
        base_confidence = 0.75

        # Increase confidence if RL and heuristic agree
        if telemetry_analysis["recommended_action"] == rl_evaluation["recommended_action"]:
            base_confidence += 0.1

        # Increase confidence for clear workload personalities
        if personality.get("personality") != "Indeterminate":
            base_confidence += 0.1

        # Decrease confidence for high-risk recommendations
        if rl_evaluation["risk_profile"] == "High":
            base_confidence -= 0.2

        return min(max(base_confidence, 0.0), 1.0)

    def _stage_baseline_update(
        self, rightsizing_recommendations: list[dict], provider: str
    ) -> dict[str, Any]:
        """
        Stage 3: Update optimization baseline in SQLite with rightsizing recommendations.
        This baseline is used for commitment management calculations.
        """
        try:
            with get_db_session() as session:
                # Clear old baseline entries for this provider
                session.query(OptimizationBaseline).filter_by(provider=provider).delete()

                # Insert new optimized baseline entries
                baseline_entries = []
                for rec in rightsizing_recommendations:
                    # Calculate optimized cost based on recommended action
                    current_sku = rec["current_sku"]
                    recommended_action = rec["recommended_action"]
                    telemetry = rec["telemetry_analysis"]

                    # Create baseline entry
                    baseline_entry = OptimizationBaseline(
                        resource_id=rec["resource_id"],
                        provider=provider,
                        current_sku=current_sku,
                        recommended_action=recommended_action,
                        environment_type=rec["environment_type"],
                        current_avg_cpu=telemetry["avg_cpu"],
                        current_avg_memory=telemetry["avg_memory"],
                        confidence_score=rec["confidence"],
                        estimated_savings=self._estimate_savings(rec, self.price_book),
                    )
                    baseline_entries.append(baseline_entry)

                session.add_all(baseline_entries)
                session.commit()

                total_estimated_savings = sum(entry.estimated_savings for entry in baseline_entries)

                return {
                    "success": True,
                    "optimized_baseline": {
                        "entry_count": len(baseline_entries),
                        "total_estimated_savings": total_estimated_savings,
                        "provider": provider,
                    },
                }

        except Exception as e:
            logger.error(f"Baseline update failed: {e}")
            return {"success": False, "error": str(e), "optimized_baseline": {}}

    def _estimate_savings(self, recommendation: dict, price_book: dict) -> float:
        """
        Estimates monthly savings for a rightsizing recommendation.
        """
        current_sku = recommendation["current_sku"]
        action = recommendation["recommended_action"]

        if action == "STAY":
            return 0.0

        # Simple estimation logic (would be enhanced with real pricing data)
        current_price = price_book.get(current_sku, 0.1)

        if "DOWN" in action or "BURSTABLE" in action:
            # Assume 50% reduction for downsize/burstable
            return current_price * 730 * 0.5

        if "SHUTDOWN" in action:
            # 100% savings for shutdown
            return current_price * 730

        return 0.0

    def _stage_commitment_management(
        self, optimized_baseline: dict, provider: str
    ) -> dict[str, Any]:
        """
        Stage 4: Calculate commitment management recommendations based on OPTIMIZED baseline.
        This prevents wasted capital by evaluating reservations AFTER rightsizing.
        """
        try:
            if not optimized_baseline.get("entry_count", 0):
                return {
                    "success": True,
                    "commitment_insights": {
                        "message": "No baseline data available for commitment analysis",
                        "recommendations": [],
                    },
                }

            # In a real implementation, this would:
            # 1. Query the optimized baseline from SQLite
            # 2. Calculate commitment coverage based on optimized usage
            # 3. Recommend RI/SP purchases based on newly optimized baseline
            # 4. Avoid the capital waste of evaluating commitments before rightsizing

            # Placeholder for commitment analysis logic
            total_savings = optimized_baseline.get("total_estimated_savings", 0)

            return {
                "success": True,
                "commitment_insights": {
                    "baseline_entries": optimized_baseline["entry_count"],
                    "optimized_monthly_spend": total_savings,
                    "commitment_recommendation": "Evaluate RIs/SPs based on optimized baseline",
                    "avoided_capital_waste": True,
                    "recommendations": [
                        {
                            "type": "Reserved Instance",
                            "reason": "Based on optimized baseline after rightsizing",
                            "potential_coverage": "High-value workloads only",
                        }
                    ],
                },
            }

        except Exception as e:
            logger.error(f"Commitment management analysis failed: {e}")
            return {"success": False, "error": str(e), "commitment_insights": {}}
