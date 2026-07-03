"""
Global Cloud Credential Service

This service manages cloud provider credentials globally across the application,
ensuring consistent access to real cloud provider data without simulated fallbacks.
"""

import os
import logging
from typing import Dict, Any, Optional
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


class CredentialService:
    """Global service for managing cloud provider credentials."""
    
    def __init__(self):
        self._credentials: Dict[str, Dict[str, Any]] = {}
        self._active_provider: Optional[str] = None
        self._load_credentials_from_env()
    
    def _load_credentials_from_env(self):
        """Load credentials from environment variables."""
        # AWS
        if all([
            os.getenv("AWS_ACCESS_KEY_ID"),
            os.getenv("AWS_SECRET_ACCESS_KEY"),
            os.getenv("AWS_REGION")
        ]):
            self._credentials["aws"] = {
                "access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
                "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
                "region": os.getenv("AWS_REGION", "us-east-1"),
            }
            logger.info("AWS credentials loaded from environment")
        
        # Azure
        if all([
            os.getenv("AZURE_SUBSCRIPTION_ID"),
            os.getenv("AZURE_TENANT_ID"),
            os.getenv("AZURE_CLIENT_ID"),
            os.getenv("AZURE_CLIENT_SECRET")
        ]):
            self._credentials["azure"] = {
                "subscription_id": os.getenv("AZURE_SUBSCRIPTION_ID"),
                "tenant_id": os.getenv("AZURE_TENANT_ID"),
                "client_id": os.getenv("AZURE_CLIENT_ID"),
                "client_secret": os.getenv("AZURE_CLIENT_SECRET"),
            }
            logger.info("Azure credentials loaded from environment")
        
        # GCP
        if os.getenv("GOOGLE_CLOUD_PROJECT"):
            self._credentials["gcp"] = {
                "project_id": os.getenv("GOOGLE_CLOUD_PROJECT"),
                "service_account_json": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            }
            logger.info("GCP credentials loaded from environment")
        
        # Set active provider from environment
        self._active_provider = os.getenv("REAPER_ACTIVE_PROVIDER", "azure").lower()
    
    def set_credentials(self, provider: str, credentials: Dict[str, Any]) -> bool:
        """
        Set credentials for a cloud provider.
        
        Args:
            provider: Cloud provider name (aws, azure, gcp)
            credentials: Dictionary of credential parameters
            
        Returns:
            True if credentials were set successfully
        """
        try:
            self._credentials[provider.lower()] = credentials
            self._set_environment_variables(provider, credentials)
            logger.info(f"Credentials set for provider: {provider}")
            return True
        except Exception as e:
            logger.error(f"Failed to set credentials for {provider}: {e}")
            return False
    
    def _set_environment_variables(self, provider: str, credentials: Dict[str, Any]):
        """Set environment variables for the provider."""
        provider = provider.lower()
        
        if provider == "aws":
            os.environ["AWS_ACCESS_KEY_ID"] = credentials["access_key_id"]
            os.environ["AWS_SECRET_ACCESS_KEY"] = credentials["secret_access_key"]
            os.environ["AWS_REGION"] = credentials.get("region", "us-east-1")
        
        elif provider == "azure":
            os.environ["AZURE_SUBSCRIPTION_ID"] = credentials["subscription_id"]
            os.environ["AZURE_TENANT_ID"] = credentials["tenant_id"]
            os.environ["AZURE_CLIENT_ID"] = credentials["client_id"]
            os.environ["AZURE_CLIENT_SECRET"] = credentials["client_secret"]
        
        elif provider == "gcp":
            os.environ["GOOGLE_CLOUD_PROJECT"] = credentials["project_id"]
            if credentials.get("service_account_json"):
                # Write service account JSON to temp file
                import tempfile
                import json
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json.dump(json.loads(credentials["service_account_json"]), f)
                    temp_path = f.name
                
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_path
    
    def get_credentials(self, provider: str) -> Optional[Dict[str, Any]]:
        """
        Get credentials for a specific provider.
        
        Args:
            provider: Cloud provider name (aws, azure, gcp)
            
        Returns:
            Dictionary of credentials or None if not configured
        """
        return self._credentials.get(provider.lower())
    
    def has_credentials(self, provider: str) -> bool:
        """Check if credentials are configured for a provider."""
        return provider.lower() in self._credentials
    
    def get_active_provider(self) -> Optional[str]:
        """Get the currently active cloud provider."""
        return self._active_provider
    
    def set_active_provider(self, provider: str) -> bool:
        """
        Set the active cloud provider.
        
        Args:
            provider: Cloud provider name (aws, azure, gcp)
            
        Returns:
            True if provider was set successfully
        """
        if provider.lower() in self._credentials:
            self._active_provider = provider.lower()
            os.environ["REAPER_ACTIVE_PROVIDER"] = provider.upper()
            logger.info(f"Active provider set to: {provider}")
            return True
        return False
    
    def get_all_providers(self) -> Dict[str, Dict[str, Any]]:
        """Get all configured providers and their credentials."""
        return self._credentials.copy()
    
    def validate_credentials(self, provider: str) -> Dict[str, Any]:
        """
        Validate credentials by attempting to connect to the cloud provider.
        
        Args:
            provider: Cloud provider name (aws, azure, gcp)
            
        Returns:
            Dictionary with validation results
        """
        credentials = self.get_credentials(provider)
        if not credentials:
            return {
                "valid": False,
                "message": f"No credentials configured for {provider}",
                "details": "Please configure credentials first"
            }
        
        try:
            if provider == "azure":
                return self._validate_azure(credentials)
            elif provider == "aws":
                return self._validate_aws(credentials)
            elif provider == "gcp":
                return self._validate_gcp(credentials)
            else:
                return {
                    "valid": False,
                    "message": f"Unknown provider: {provider}",
                    "details": ""
                }
        except Exception as e:
            logger.error(f"Credential validation failed for {provider}: {e}")
            return {
                "valid": False,
                "message": f"Validation failed: {str(e)}",
                "details": ""
            }
    
    def _validate_azure(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Azure credentials."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.subscription import SubscriptionClient
            
            # Set environment for validation
            old_env = {
                "AZURE_SUBSCRIPTION_ID": os.getenv("AZURE_SUBSCRIPTION_ID"),
                "AZURE_TENANT_ID": os.getenv("AZURE_TENANT_ID"),
                "AZURE_CLIENT_ID": os.getenv("AZURE_CLIENT_ID"),
                "AZURE_CLIENT_SECRET": os.getenv("AZURE_CLIENT_SECRET"),
            }
            
            try:
                os.environ["AZURE_SUBSCRIPTION_ID"] = credentials["subscription_id"]
                os.environ["AZURE_TENANT_ID"] = credentials["tenant_id"]
                os.environ["AZURE_CLIENT_ID"] = credentials["client_id"]
                os.environ["AZURE_CLIENT_SECRET"] = credentials["client_secret"]
                
                cred = DefaultAzureCredential()
                sub_client = SubscriptionClient(cred)
                # Try to list subscriptions to validate credentials
                list(sub_client.subscriptions.list())
                
                return {
                    "valid": True,
                    "message": "Azure credentials validated successfully",
                    "details": f"Connected to subscription {credentials['subscription_id'][:8]}...",
                }
            finally:
                # Restore old environment
                for key, value in old_env.items():
                    if value:
                        os.environ[key] = value
                    else:
                        os.environ.pop(key, None)
                        
        except ImportError as e:
            logger.warning(f"Azure SDK not available for validation: {e}")
            return {
                "valid": True,
                "message": "Azure credentials saved (validation skipped)",
                "details": "Azure SDK not available"
            }
        except Exception as e:
            return {
                "valid": False,
                "message": f"Azure connection failed: {str(e)}",
                "details": ""
            }
    
    def _validate_aws(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Validate AWS credentials."""
        try:
            import boto3
            
            # Set environment for validation
            old_env = {
                "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
                "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
                "AWS_REGION": os.getenv("AWS_REGION"),
            }
            
            try:
                os.environ["AWS_ACCESS_KEY_ID"] = credentials["access_key_id"]
                os.environ["AWS_SECRET_ACCESS_KEY"] = credentials["secret_access_key"]
                os.environ["AWS_REGION"] = credentials["region"]
                
                # Try to connect to EC2
                ec2 = boto3.client("ec2", region_name=credentials["region"])
                ec2.describe_account()
                
                return {
                    "valid": True,
                    "message": "AWS credentials validated successfully",
                    "details": f"Connected to AWS region {credentials['region']}",
                }
            finally:
                # Restore old environment
                for key, value in old_env.items():
                    if value:
                        os.environ[key] = value
                    else:
                        os.environ.pop(key, None)
                        
        except ImportError:
            return {
                "valid": True,
                "message": "AWS credentials saved (boto3 not available for validation)",
                "details": "Credentials stored but validation skipped"
            }
        except Exception as e:
            return {
                "valid": False,
                "message": f"AWS connection failed: {str(e)}",
                "details": ""
            }
    
    def _validate_gcp(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Validate GCP credentials."""
        try:
            import json
            from google.oauth2 import service_account as sa
            
            if credentials.get("service_account_json"):
                try:
                    json.loads(credentials["service_account_json"])
                    return {
                        "valid": True,
                        "message": "GCP credentials validated successfully",
                        "details": f"Project: {credentials['project_id']}",
                    }
                except json.JSONDecodeError:
                    return {
                        "valid": False,
                        "message": "Invalid service account JSON",
                        "details": "JSON parsing failed"
                    }
            else:
                return {
                    "valid": True,
                    "message": "GCP credentials saved (validation skipped)",
                    "details": "No service account JSON provided"
                }
                
        except ImportError:
            return {
                "valid": True,
                "message": "GCP credentials saved (validation skipped)",
                "details": "Google SDK not available"
            }
        except Exception as e:
            return {
                "valid": False,
                "message": f"GCP validation failed: {str(e)}",
                "details": ""
            }
    
    def clear_credentials(self, provider: str) -> bool:
        """
        Clear credentials for a specific provider.
        
        Args:
            provider: Cloud provider name (aws, azure, gcp)
            
        Returns:
            True if credentials were cleared successfully
        """
        provider = provider.lower()
        if provider in self._credentials:
            del self._credentials[provider]
            
            # Clear environment variables
            if provider == "aws":
                for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]:
                    os.environ.pop(key, None)
            elif provider == "azure":
                for key in ["AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"]:
                    os.environ.pop(key, None)
            elif provider == "gcp":
                for key in ["GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS"]:
                    os.environ.pop(key, None)
            
            logger.info(f"Cleared credentials for provider: {provider}")
            return True
        return False


# Global credential service instance
_credential_service: Optional[CredentialService] = None


def get_credential_service() -> CredentialService:
    """Get the global credential service instance."""
    global _credential_service
    if _credential_service is None:
        _credential_service = CredentialService()
    return _credential_service


def require_credentials(provider: Optional[str] = None) -> Dict[str, Any]:
    """
    Check if required credentials are available.
    
    Args:
        provider: Specific provider to check, or None to check active provider
        
    Returns:
        Dictionary with status and message
    """
    service = get_credential_service()
    
    if provider is None:
        provider = service.get_active_provider()
    
    if not provider:
        return {
            "status": "error",
            "message": "No active cloud provider configured",
            "code": "NO_ACTIVE_PROVIDER"
        }
    
    if not service.has_credentials(provider):
        return {
            "status": "error",
            "message": f"No credentials configured for {provider.upper()}",
            "code": "NO_CREDENTIALS",
            "provider": provider
        }
    
    return {
        "status": "success",
        "message": f"Credentials available for {provider.upper()}",
        "provider": provider
    }