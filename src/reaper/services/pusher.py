"""
Data Pusher Module - Telemetry and savings data pusher.
Supports local database storage and extensible telemetry backends.
"""

import logging
import os
from datetime import UTC, datetime

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
        resource_id: str | None = None,
        action_type: str | None = None,
        metadata: dict | None = None,
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
            if self.backend == "prometheus":
                return self._push_to_prometheus(
                    provider, amount, resource_id, action_type, metadata
                )
            logger.warning(f"Unknown backend: {self.backend}")
            return False
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid data format for savings push: {e}")
            return False
        except OSError as e:
            logger.error(f"I/O error pushing savings data: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error pushing savings data: {e}")
            return False

    def _push_to_local_db(
        self,
        provider: str,
        amount: float,
        resource_id: str | None,
        action_type: str | None,
        metadata: dict | None,
    ) -> bool:
        """Push savings data to local SQLite database.

        This stores savings records in the cost_history table for tracking.
        """
        try:
            from reaper.engine.models.resources import CostHistory, SessionLocal

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
                    timestamp=datetime.now(UTC),
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
            logger.info(
                f"[SAVINGS] Provider: {provider}, Amount: ${amount:.2f}, "
                f"Resource: {resource_id}, Action: {action_type}"
            )
            return True

    def _push_to_prometheus(
        self,
        provider: str,
        amount: float,
        resource_id: str | None,
        action_type: str | None,
        metadata: dict | None,
    ) -> bool:
        """Push savings data to Prometheus Pushgateway.

        This method pushes savings metrics to Prometheus using the Pushgateway.
        It creates custom metrics for savings tracking by provider and action type,
        includes resource_id and action_type as metric labels, and handles connection errors.
        """
        try:
            from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
            
            # Get Prometheus pushgateway URL from environment
            pushgateway_url = os.getenv("PROMETHEUS_PUSHGATEWAY_URL", "localhost:9091")
            job_name = os.getenv("PROMETHEUS_JOB_NAME", "cloud-reaper")
            
            # Create a collector registry for this push
            registry = CollectorRegistry()
            
            # Create a gauge metric for savings
            savings_gauge = Gauge(
                'cloud_reaper_savings',
                'Savings achieved by Cloud Reaper',
                ['provider', 'action_type', 'resource_id'],
                registry=registry
            )
            
            # Set the gauge value with labels
            labels = {
                'provider': provider,
                'action_type': action_type or 'unknown',
                'resource_id': resource_id or 'unknown'
            }
            savings_gauge.labels(**labels).set(amount)
            
            # Push to Prometheus Pushgateway
            push_to_gateway(pushgateway_url, job=job_name, registry=registry)
            
            logger.info(
                f"Successfully pushed to Prometheus: provider={provider}, amount=${amount:.2f}, "
                f"resource_id={resource_id}, action_type={action_type}"
            )
            return True
            
        except ImportError:
            logger.warning(
                "prometheus_client not installed. "
                "Install it with: pip install prometheus_client"
            )
            # Fallback to logging if prometheus_client is not available
            logger.info(
                f"[SAVINGS] Provider: {provider}, Amount: ${amount:.2f}, "
                f"Resource: {resource_id}, Action: {action_type}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to push to Prometheus: {e}")
            # Fallback to logging on error
            logger.info(
                f"[SAVINGS] Provider: {provider}, Amount: ${amount:.2f}, "
                f"Resource: {resource_id}, Action: {action_type}"
            )
            return False

    def push_metric(
        self,
        metric_name: str,
        value: float,
        labels: dict | None = None,
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
            if self.backend == "prometheus":
                return self._push_metric_to_prometheus(metric_name, value, labels)
            else:
                logger.debug(f"Pushing metric: {metric_name}={value} labels={labels}")
                return True
        except Exception as e:
            logger.error(f"Failed to push metric: {e}")
            return False

    def _push_metric_to_prometheus(
        self,
        metric_name: str,
        value: float,
        labels: dict | None = None,
    ) -> bool:
        """Push a generic metric to Prometheus Pushgateway."""
        try:
            from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
            
            # Get Prometheus pushgateway URL from environment
            pushgateway_url = os.getenv("PROMETHEUS_PUSHGATEWAY_URL", "localhost:9091")
            job_name = os.getenv("PROMETHEUS_JOB_NAME", "cloud-reaper")
            
            # Create a collector registry for this push
            registry = CollectorRegistry()
            
            # Sanitize metric name (Prometheus requirements)
            sanitized_name = metric_name.replace("-", "_").replace(" ", "_")
            
            # Create a gauge metric
            metric_gauge = Gauge(
                sanitized_name,
                f'Cloud Reaper metric: {metric_name}',
                list(labels.keys()) if labels else [],
                registry=registry
            )
            
            # Set the gauge value with labels
            if labels:
                metric_gauge.labels(**labels).set(value)
            else:
                metric_gauge.set(value)
            
            # Push to Prometheus Pushgateway
            push_to_gateway(pushgateway_url, job=job_name, registry=registry)
            
            logger.info(f"Successfully pushed metric to Prometheus: {metric_name}={value}")
            return True
            
        except ImportError:
            logger.warning(
                "prometheus_client not installed. "
                "Install it with: pip install prometheus_client"
            )
            # Fallback to logging
            logger.info(f"[METRIC] {metric_name}={value} labels={labels}")
            return True
        except Exception as e:
            logger.error(f"Failed to push metric to Prometheus: {e}")
            # Fallback to logging
            logger.info(f"[METRIC] {metric_name}={value} labels={labels}")
            return False

    def close(self) -> None:
        """Close the data pusher and cleanup resources."""
        if not self._closed:
            logger.info("Closing DataPusher")
            self._closed = True
            # Cleanup any open connections or resources
