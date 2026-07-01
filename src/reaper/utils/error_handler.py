"""
Centralized Error Handling and Logging Module
Provides structured logging, error recovery suggestions, and error reporting.
"""

import logging
import sys
import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

# Configure structured logging
class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ErrorCategory(Enum):
    """Categories of errors for better classification and recovery."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NETWORK = "network"
    DATABASE = "database"
    CLOUD_PROVIDER = "cloud_provider"
    VALIDATION = "validation"
    INTERNAL = "internal"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"


class ErrorRecovery:
    """Error recovery suggestions based on error category."""
    
    SUGGESTIONS = {
        ErrorCategory.AUTHENTICATION: [
            "Verify your API credentials are correct",
            "Check that your API keys haven't expired",
            "Ensure you have the necessary permissions",
            "Try regenerating your API keys"
        ],
        ErrorCategory.AUTHORIZATION: [
            "Verify you have the required permissions",
            "Check your role assignments",
            "Contact your administrator for access",
            "Review resource access policies"
        ],
        ErrorCategory.NETWORK: [
            "Check your internet connection",
            "Verify firewall settings allow outbound connections",
            "Check if the service endpoint is reachable",
            "Try again after a few moments"
        ],
        ErrorCategory.DATABASE: [
            "Verify the database file exists and is accessible",
            "Check database file permissions",
            "Ensure sufficient disk space",
            "Try restarting the application"
        ],
        ErrorCategory.CLOUD_PROVIDER: [
            "Verify cloud provider credentials are configured",
            "Check if the cloud service is operational",
            "Verify subscription/tenant IDs are correct",
            "Check cloud provider status page for outages"
        ],
        ErrorCategory.VALIDATION: [
            "Review the input data format",
            "Check required fields are provided",
            "Verify data types match expected values",
            "Refer to API documentation for correct format"
        ],
        ErrorCategory.INTERNAL: [
            "Check application logs for details",
            "Report this issue to the development team",
            "Try restarting the application",
            "Ensure you're using the latest version"
        ],
        ErrorCategory.RATE_LIMIT: [
            "Reduce request frequency",
            "Implement exponential backoff",
            "Wait a few minutes before retrying",
            "Consider upgrading your API tier"
        ],
        ErrorCategory.TIMEOUT: [
            "Check network connectivity",
            "Increase timeout duration if possible",
            "Verify the service is responding",
            "Try the operation again"
        ]
    }


class StructuredLogger:
    """Structured logger with consistent formatting and context."""
    
    def __init__(self, name: str, level: LogLevel = LogLevel.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.value))
        
        # Avoid duplicate handlers
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _log(
        self,
        level: LogLevel,
        message: str,
        category: Optional[ErrorCategory] = None,
        context: Optional[dict[str, Any]] = None,
        exc_info: Optional[bool] = False
    ):
        """Internal logging method with structured context."""
        log_data = {"message": message}
        
        if category:
            log_data["category"] = category.value
        
        if context:
            log_data.update(context)
        
        # Format as structured log
        formatted_message = f"{message}"
        if category:
            formatted_message += f" [category: {category.value}]"
        if context:
            context_str = ", ".join(f"{k}={v}" for k, v in context.items())
            formatted_message += f" [context: {context_str}]"
        
        getattr(self.logger, level.value.lower())(formatted_message, exc_info=exc_info)
    
    def debug(self, message: str, **kwargs):
        self._log(LogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log(LogLevel.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log(LogLevel.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log(LogLevel.ERROR, message, exc_info=kwargs.pop('exc_info', False), **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log(LogLevel.CRITICAL, message, exc_info=kwargs.pop('exc_info', True), **kwargs)


class ErrorHandler:
    """Centralized error handler with recovery suggestions and reporting."""
    
    def __init__(self):
        self.logger = StructuredLogger("ErrorHandler")
        self.error_history: list[dict[str, Any]] = []
    
    def handle_error(
        self,
        error: Exception,
        category: ErrorCategory,
        context: Optional[dict[str, Any]] = None,
        user_message: Optional[str] = None
    ) -> dict[str, Any]:
        """Handle an error with logging, recovery suggestions, and reporting."""
        
        # Extract error details
        error_details = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "category": category.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "traceback": traceback.format_exc() if self.logger.logger.level <= logging.DEBUG else None,
            "context": context or {}
        }
        
        # Log the error
        self.logger.error(
            f"{error_details['error_type']}: {error_details['error_message']}",
            category=category,
            context=context,
            exc_info=True
        )
        
        # Store in history
        self.error_history.append(error_details)
        
        # Generate user-friendly message
        if not user_message:
            user_message = self._generate_user_message(category)
        
        # Get recovery suggestions
        suggestions = ErrorRecovery.SUGGESTIONS.get(category, [])
        
        # Build response
        response = {
            "status": "error",
            "error_type": error_details['error_type'],
            "message": user_message,
            "category": category.value,
            "suggestions": suggestions,
            "timestamp": error_details['timestamp']
        }
        
        if context:
            response["context"] = context
        
        return response
    
    def _generate_user_message(self, category: ErrorCategory) -> str:
        """Generate user-friendly error message based on category."""
        messages = {
            ErrorCategory.AUTHENTICATION: "Authentication failed. Please verify your credentials.",
            ErrorCategory.AUTHORIZATION: "You don't have permission to perform this action.",
            ErrorCategory.NETWORK: "Network error occurred. Please check your connection.",
            ErrorCategory.DATABASE: "Database error occurred. Please try again.",
            ErrorCategory.CLOUD_PROVIDER: "Cloud provider error occurred. Please verify your configuration.",
            ErrorCategory.VALIDATION: "Invalid input provided. Please check your data.",
            ErrorCategory.INTERNAL: "An internal error occurred. Please try again or contact support.",
            ErrorCategory.RATE_LIMIT: "Rate limit exceeded. Please wait before retrying.",
            ErrorCategory.TIMEOUT: "Operation timed out. Please try again."
        }
        return messages.get(category, "An error occurred. Please try again.")
    
    def get_error_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent error history."""
        return self.error_history[-limit:]
    
    def clear_error_history(self):
        """Clear error history."""
        self.error_history.clear()
        self.logger.info("Error history cleared")


# Global error handler instance
error_handler = ErrorHandler()


def handle_exception(
    error: Exception,
    category: ErrorCategory,
    context: Optional[dict[str, Any]] = None,
    user_message: Optional[str] = None
) -> dict[str, Any]:
    """Convenience function to handle exceptions using the global error handler."""
    return error_handler.handle_error(error, category, context, user_message)


def get_logger(name: str, level: LogLevel = LogLevel.INFO) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name, level)
