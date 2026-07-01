"""
Data Pusher Module - Telemetry and savings data pusher.
Supports local database storage and extensible telemetry backends.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class DataPusher:
    """Data pusher for telemetry and savings data with extensible backends."""

    def __init__(self, backend: str = "local"):
        """Initialize the data pusher.
        
        Args:
            backend: Storage backend - 'local' for database, 'prometheus' for remote telemetry
        """
        self.backend = backend
        self._closed = False
        logger.info(f"DataPusher initialized with backend: {backend}")

    def push_savings(
        self,
        provider: str,
        amount: float,
        resource_id: Optional[str] = None,
        action_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Push savings data to the configured backend.
        
        Args:
            provider: Cloud provider (azure, aws, gcp)
            amount: Savings amount in USD
            resource_id: Optional resource identifier
            action_type: Type of action that generated savings (deallocate, resize, etc.)
            metadata: Optional additional metadata
            
        Returns:
            True if push was successful, False otherwise
        """
        if self._closed:
            logger.warning("DataPusher is closed, cannot push data")
            return False

        try:
            if self.backend == "local":
                return self._push_to_local_db(provider, amount, resource_id, action_type, metadata)
            elif self.backend == "prometheus":
                return self._push_to_prometheus(provider, amount, resource_id, action_type, metadata)
            else:
                logger.warning(f"Unknown backend: {self.backend}")
                return False
        except Exception as e:
            logger.error(f"Failed to push savings data: {e}")
            return False

    def _push_to_local_db(
        self,
        provider: str,
        amount: float,
        resource_id: Optional[str],
        action_type: Optional[str],
        metadata: Optional[dict],
    ) -> bool:
        """Push savings data to local SQLite database.
        
        This stores savings records in the cost_history table for tracking.
        """
        try:
            from reaper.engine.models.resources import SessionLocal, CostHistory
            
            session = SessionLocal()
            try:
                # Create a cost history entry for the savings
                savings_record = CostHistory(
                    resource_id=resource_id or f"savings_{provider}_{datetime.now().timestamp()}",
                    provider=provider,
                    cost_category="savings",
                    actual_cost=-amount,  # Negative cost represents savings
                    amortized_cost=-amount,
                    currency="USD",
                    timestamp=datetime.now(timezone.utc),
                )
                
                session.add(savings_record)
                session.commit()
                
                logger.info(f"Saved ${amount:.2f} from {provider} to local database")
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Database error saving savings: {e}")
                return False
            finally:
                session.close()
        except ImportError:
            logger.warning("Database models not available, using fallback logging")
            # Fallback to logging if database is not available
            logger.info(f"[SAVINGS] Provider: {provider}, Amount: ${amount:.2f}, "
                       f"Resource: {resource_id}, Action: {action_type}")
            return True

    def _push_to_prometheus(
        self,
        provider: str,
        amount: float,
        resource_id: Optional[str],
        action_type: Optional[str],
        metadata: Optional[dict],
    ) -> bool:
        """Push savings data to Prometheus (placeholder for future implementation).
        
        This method is a placeholder for future Prometheus integration.
        """
        logger.info(f"Prometheus backend not yet implemented. "
                   f"Would push: provider={provider}, amount={amount}, "
                   f"resource_id={resource_id}, action_type={action_type}")
        # TODO: Implement Prometheus client integration
        return True

    def push_metric(
        self,
        metric_name: str,
        value: float,
        labels: Optional[dict] = None,
    ) -> bool:
        """Push a generic metric to the configured backend.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            labels: Optional metric labels
            
        Returns:
            True if push was successful, False otherwise
        """
        if self._closed:
            logger.warning("DataPusher is closed, cannot push data")
            return False

        try:
            logger.debug(f"Pushing metric: {metric_name}={value} labels={labels}")
            # For now, just log the metric
            # Future implementations can push to Prometheus, Grafana, etc.
            return True
        except Exception as e:
            logger.error(f"Failed to push metric: {e}")
            return False

    def close(self) -> None:
        """Close the data pusher and cleanup resources."""
        if not self._closed:
            logger.info("Closing DataPusher")
            self._closed = True
            # Cleanup any open connections or resources
