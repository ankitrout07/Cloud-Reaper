import json
import os

import requests
from openai import OpenAI
from pydantic import BaseModel, Field


_AWS_PRICES_CACHE = None
_GCP_PRICES_CACHE = None


# Define the strict structure for each infrastructure component
class CloudComponent(BaseModel):
    component_type: str = Field(
        description="The structural category: compute, database, storage, or networking"
    )
    generic_name: str = Field(description="Friendly name, e.g., Managed Kubernetes, Block Storage")
    provider_sku_keyword: str = Field(
        description="The exact instance type or SKU keyword, e.g., t3.medium, Standard_D2_v5, db-f1-micro"
    )
    quantity: int = Field(
        description="Number of units needed to satisfy the capacity or high-availability requirements"
    )
    reasoning: str = Field(
        description="A brief explanation of why this size or resource tier was selected"
    )


# Define the top-level schema contract that the LLM must return
class ArchitectureBlueprint(BaseModel):
    architecture_summary: str = Field(
        description="High-level overview of how this deployment works"
    )
    components: list[CloudComponent] = Field(
        description="The precise list of required infrastructure components"
    )
    security_warning: str | None = Field(
        None, description="Any critical architectural or security warnings for this stack"
    )


def _generate_local_fallback(user_prompt: str, provider: str) -> ArchitectureBlueprint:
    prompt_lower = user_prompt.lower()
    components = []

    # Define provider-specific SKUs matching real database options
    skus = {
        "azure": {
            "compute": "standard_d2_v5",
            "compute_name": "Azure Virtual Machine (General Purpose)",
            "k8s": "Standard_D4s_v5",
            "k8s_name": "Azure Kubernetes Service (AKS) Nodes",
            "db": "standard_e2_v5",
            "db_name": "Azure Database for PostgreSQL (Flexible)",
            "storage": "blob_hot",
            "storage_name": "Azure Blob Storage (Hot Tier)",
            "net": "standard_sig_v5",
            "net_name": "Azure Virtual Network & Gateway",
        },
        "aws": {
            "compute": "t3.medium",
            "compute_name": "Amazon EC2 Instance (t3.medium)",
            "k8s": "m5.large",
            "k8s_name": "Amazon EKS Worker Nodes (m5.large)",
            "db": "db.t3.medium",
            "db_name": "Amazon RDS for PostgreSQL",
            "storage": "s3_standard",
            "storage_name": "Amazon S3 Standard Bucket",
            "net": "t3.micro",
            "net_name": "Amazon VPC & NAT Gateway",
        },
        "gcp": {
            "compute": "e2-standard-2",
            "compute_name": "Google Compute Engine VM (e2-standard-2)",
            "k8s": "n2-standard-2",
            "k8s_name": "Google Kubernetes Engine (GKE) Cluster",
            "db": "db-custom-2-7680",
            "db_name": "Google Cloud SQL Instance",
            "storage": "gcs_standard",
            "storage_name": "Google Cloud Storage Bucket",
            "net": "e2-standard-2",
            "net_name": "Google Cloud VPC & NAT Gateway",
        },
    }

    prov = provider.lower()
    if prov not in skus:
        prov = "azure"
    cfg = skus[prov]

    # 1. Compute layer
    if any(k in prompt_lower for k in ["kubernetes", "k8s", "cluster", "aks", "eks", "gke"]):
        components.append(
            CloudComponent(
                component_type="compute",
                generic_name=cfg["k8s_name"],
                provider_sku_keyword=cfg["k8s"],
                quantity=3 if any(h in prompt_lower for h in ["ha", "prod", "high"]) else 2,
                reasoning="Configured highly-available container orchestration cluster node pool matching containerized workload requirements.",
            )
        )
    else:
        components.append(
            CloudComponent(
                component_type="compute",
                generic_name=cfg["compute_name"],
                provider_sku_keyword=cfg["compute"],
                quantity=2 if any(h in prompt_lower for h in ["ha", "prod", "high"]) else 1,
                reasoning="Provisioned general-purpose virtual machine compute instances to host core application layer.",
            )
        )

    # 2. Database layer
    if any(k in prompt_lower for k in ["db", "database", "sql", "postgres", "mysql", "mongo"]):
        components.append(
            CloudComponent(
                component_type="database",
                generic_name=cfg["db_name"],
                provider_sku_keyword=cfg["db"],
                quantity=2 if any(h in prompt_lower for h in ["ha", "prod", "high"]) else 1,
                reasoning="Configured managed transactional database instances with point-in-time recovery and warm standby replication.",
            )
        )

    # 3. Storage layer
    if any(k in prompt_lower for k in ["storage", "bucket", "s3", "blob", "file"]):
        components.append(
            CloudComponent(
                component_type="storage",
                generic_name=cfg["storage_name"],
                provider_sku_keyword=cfg["storage"],
                quantity=1,
                reasoning="Assigned decoupled object store storage capacity for static assets, user uploads, and transaction logs.",
            )
        )

    # 4. Networking layer
    components.append(
        CloudComponent(
            component_type="networking",
            generic_name=cfg["net_name"],
            provider_sku_keyword=cfg["net"],
            quantity=1,
            reasoning="Established secure network boundary, subnet routes, and gateway firewall to secure traffic.",
        )
    )

    summary = f"Synthesized production-grade {provider.upper()} architecture blueprint designed by Cloud-Reaper local offline model. Designed to satisfy workload SLA capacity spec."
    warning = "Notice: Running in Local Offline Synthesizer Fallback Mode due to external AI API rate-limits/quota depletion."

    return ArchitectureBlueprint(
        architecture_summary=summary, components=components, security_warning=warning
    )


class AIArchitectManager:
    def __init__(self):
        # Gracefully pull the API keys from your environment setup
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.client = None

    def verify_api_status(self) -> dict:
        """
        Verifies both OpenAI and Gemini API Key statuses.
        Returns:
            dict containing status of 'openai' and 'gemini' keys: 'active', 'invalid', 'unconfigured'
        """
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")

        status = {"openai": "unconfigured", "gemini": "unconfigured"}

        # Verify OpenAI
        if self.openai_key and self.openai_key != "your_actual_openai_api_key_here":
            try:
                self.client = OpenAI(api_key=self.openai_key)
                self.client.models.list()
                status["openai"] = "active"
            except Exception:
                status["openai"] = "invalid"

        # Verify Gemini
        if self.gemini_key and self.gemini_key != "your_actual_gemini_api_key_here":
            try:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={self.gemini_key}"
                )
                res = requests.get(url, timeout=5)
                if res.status_code == 200:
                    status["gemini"] = "active"
                else:
                    status["gemini"] = "invalid"
            except Exception:
                status["gemini"] = "invalid"

        return status

    def generate_blueprint(
        self, user_prompt: str, provider: str, model_provider: str = "openai"
    ) -> ArchitectureBlueprint:
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")

        system_instructions = (
            f"You are the Principal Cloud Architect engine for Cloud-Reaper. "
            f"Analyze the user request and design a cost-optimized, production-ready cloud architecture "
            f"exclusively using {provider.upper()} services. You must follow the requested provider strictly. "
            f"Do not mix providers. Output your response as a pristine structured JSON object matching the schema. "
            f"Crucial: For the provider_sku_keyword field, always use standard, recognizable cloud VM sizes or SKU keywords "
            f"(e.g., standard_d2_v5, standard_e2_v5, standard_sig_v5, or blob_hot for Azure; "
            f"t3.medium, m5.large, t3.micro, or s3_standard for AWS; "
            f"e2-standard-2, n2-standard-2, or gcs_standard for GCP) "
            f"so that they map perfectly to regional price databases."
        )

        try:
            if model_provider == "gemini" or (not self.openai_key and self.gemini_key):
                if not self.gemini_key or self.gemini_key == "your_actual_gemini_api_key_here":
                    raise ValueError("GEMINI_API_KEY is not set in the environment variables.")

                # Call Gemini Structured Output API
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": system_instructions}, {"text": user_prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseSchema": {
                            "type": "OBJECT",
                            "properties": {
                                "architecture_summary": {"type": "STRING"},
                                "components": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "component_type": {"type": "STRING"},
                                            "generic_name": {"type": "STRING"},
                                            "provider_sku_keyword": {"type": "STRING"},
                                            "quantity": {"type": "INTEGER"},
                                            "reasoning": {"type": "STRING"},
                                        },
                                        "required": [
                                            "component_type",
                                            "generic_name",
                                            "provider_sku_keyword",
                                            "quantity",
                                            "reasoning",
                                        ],
                                    },
                                },
                                "security_warning": {"type": "STRING"},
                            },
                            "required": ["architecture_summary", "components"],
                        },
                    },
                }
                res = requests.post(
                    url, json=payload, headers={"Content-Type": "application/json"}, timeout=30
                )
                if res.status_code != 200:
                    raise ValueError(f"Gemini API returned error: {res.text}")

                data = res.json()
                try:
                    text_content = data["candidates"][0]["content"]["parts"][0]["text"]
                    blueprint_dict = json.loads(text_content)
                    return ArchitectureBlueprint(**blueprint_dict)
                except Exception as e:
                    raise ValueError(f"Failed to parse structured response from Gemini API: {e!s}")
            else:
                if not self.openai_key or self.openai_key == "your_actual_openai_api_key_here":
                    raise ValueError("OPENAI_API_KEY is not set in the environment variables.")

                self.client = OpenAI(api_key=self.openai_key)
                response = self.client.beta.chat.completions.parse(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_instructions},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format=ArchitectureBlueprint,
                )
                return response.choices[0].message.parsed
        except Exception as e:
            print(f"[!] AI synthesis error: {e!s}. Activating local offline fallback generator.")
            return _generate_local_fallback(user_prompt, provider)


def resolve_component_costs(blueprint_data, provider: str, region: str) -> dict:
    """
    Takes the structured LLM blueprint, queries the region_price_cache table,
    calculates monthly operational metrics, and applies a resilient fallback matrix.
    """
    global _AWS_PRICES_CACHE, _GCP_PRICES_CACHE
    total_monthly_cost = 0.0
    calculated_components = []

    # High-fidelity static fallback matrix for development/offline parity
    # Keeps your dashboard functional even if the Go core hasn't cached the SKU yet
    price_fallbacks = {
        "azure": {
            "standard_sig_v5": 0.096,
            "standard_d2_v5": 0.096,
            "standard_e2_v5": 0.130,
            "blob_hot": 0.020,
            "azure virtual machines": 0.096,
            "azure database for postgresql": 0.130,
            "azure sql database": 0.130,
            "azure storage": 0.020,
            "azure virtual network": 0.005,
            "azure public ip address": 0.004,
            "azure network security group": 0.001,
            "azure load balancer": 0.025,
            "azure app service": 0.080,
            "azure container registry": 0.010,
            "azure key vault": 0.003,
            "azure monitor": 0.005,
            "application insights": 0.005,
        },
        "aws": {
            "t3.medium": 0.0416,
            "m5.large": 0.096,
            "t3.micro": 0.0104,
            "s3_standard": 0.023,
            "ec2": 0.0416,
            "rds": 0.080,
            "s3": 0.023,
            "vpc": 0.005,
            "nat gateway": 0.045,
            "elastic load balancing": 0.025,
            "route 53": 0.001,
            "cloudwatch": 0.005,
        },
        "gcp": {
            "e2-standard-2": 0.067,
            "n2-standard-2": 0.097,
            "gcs_standard": 0.020,
            "compute engine": 0.067,
            "cloud sql": 0.100,
            "cloud storage": 0.020,
            "vpc network": 0.005,
            "cloud load balancing": 0.025,
            "cloud dns": 0.001,
            "operations suite": 0.005,
        },
    }

    # Region mapping to handle standard pricing queries correctly
    region_mapping = {
        "azure": {
            "eastus": "eastus",
            "westus2": "westus2",
            "westeurope": "westeurope",
            "uksouth": "uksouth",
            "centralindia": "centralindia",
            "southeastasia": "southeastasia",
            "australiaeast": "australiaeast",
            "brazilsouth": "brazilsouth"
        },
        "aws": {
            "eastus": "us-east-1",
            "westus2": "us-west-2",
            "westeurope": "eu-west-1",
            "uksouth": "eu-west-2",
            "centralindia": "ap-south-1",
            "southeastasia": "ap-southeast-1",
            "australiaeast": "ap-southeast-2",
            "brazilsouth": "sa-east-1"
        },
        "gcp": {
            "eastus": "us-east1",
            "westus2": "us-west2",
            "westeurope": "europe-west1",
            "uksouth": "europe-west2",
            "centralindia": "asia-south1",
            "southeastasia": "asia-southeast1",
            "australiaeast": "australia-southeast1",
            "brazilsouth": "southamerica-east1"
        }
    }

    provider_fallbacks = price_fallbacks.get(provider.lower(), {})
    mapped_region = region_mapping.get(provider.lower(), {}).get(region.lower(), region)

    for item in blueprint_data.components:
        sku = item.provider_sku_keyword.strip()
        quantity = item.quantity if item.quantity > 0 else 1
        hourly_rate = None

        # --- DATABASE QUERY BLOCK ---
        try:
            from reaper.engine.models import SessionLocal, RegionPriceCache
            db = SessionLocal()
            db_record = db.query(RegionPriceCache).filter(
                RegionPriceCache.region_name == region
            ).filter(
                (RegionPriceCache.sku_id.ilike(sku)) | (RegionPriceCache.sku_id.ilike(f"%{sku}%"))
            ).first()
            
            if db_record:
                hourly_rate = float(db_record.price)
            db.close()
        except Exception:
            hourly_rate = None

        # --- REAL-TIME API PRICING DOCK ---
        if hourly_rate is None:
            if provider.lower() == "azure":
                try:
                    from reaper.collectors.azure_prices import AzurePriceClient
                    client = AzurePriceClient()
                    clean_sku = sku
                    if clean_sku.lower().startswith("standard_"):
                        parts = clean_sku.split("_")
                        clean_sku = "Standard_" + "_".join(parts[1:])
                    
                    query = f"armSkuName eq '{clean_sku}' and armRegionName eq '{mapped_region}' and priceType eq 'Consumption'"
                    res = client.get_prices(filter_query=query)
                    if not res:
                        query = f"armSkuName eq '{sku}' and priceType eq 'Consumption'"
                        res = client.get_prices(filter_query=query)
                    
                    if res:
                        best_price = next((r for r in res if not r.get("reservationTerm")), res[0])
                        hourly_rate = float(best_price.get("retailPrice", 0))
                        
                        # Cache in DB
                        try:
                            from reaper.engine.models import SessionLocal, RegionPriceCache
                            db = SessionLocal()
                            db.query(RegionPriceCache).filter_by(sku_id=sku, region_name=region).delete()
                            new_cache = RegionPriceCache(
                                sku_id=sku,
                                region_name=region,
                                price=hourly_rate,
                                currency="USD"
                            )
                            db.add(new_cache)
                            db.commit()
                            db.close()
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[!] Real-time Azure pricing fetch failed: {e}")

            elif provider.lower() == "aws":
                try:
                    if _AWS_PRICES_CACHE is None:
                        from reaper.collectors.aws_prices import AWSPriceClient
                        aws_client = AWSPriceClient()
                        _AWS_PRICES_CACHE = aws_client.get_live_prices()
                    
                    match = next((p for p in _AWS_PRICES_CACHE if p["skuName"].lower() == sku.lower() and p["armRegionName"] == mapped_region), None)
                    if match:
                        hourly_rate = float(match["retailPrice"])
                        
                        # Cache in DB
                        try:
                            from reaper.engine.models import SessionLocal, RegionPriceCache
                            db = SessionLocal()
                            db.query(RegionPriceCache).filter_by(sku_id=sku, region_name=region).delete()
                            new_cache = RegionPriceCache(
                                sku_id=sku,
                                region_name=region,
                                price=hourly_rate,
                                currency="USD"
                            )
                            db.add(new_cache)
                            db.commit()
                            db.close()
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[!] Real-time AWS pricing fetch failed: {e}")

            elif provider.lower() == "gcp":
                try:
                    if _GCP_PRICES_CACHE is None:
                        from reaper.collectors.gcp_prices import GCPPriceClient
                        gcp_client = GCPPriceClient()
                        _GCP_PRICES_CACHE = gcp_client.get_live_prices()
                    
                    match = next((p for p in _GCP_PRICES_CACHE if p["skuName"].lower() == sku.lower() and p["armRegionName"] == mapped_region), None)
                    if match:
                        hourly_rate = float(match["retailPrice"])
                        
                        # Cache in DB
                        try:
                            from reaper.engine.models import SessionLocal, RegionPriceCache
                            db = SessionLocal()
                            db.query(RegionPriceCache).filter_by(sku_id=sku, region_name=region).delete()
                            new_cache = RegionPriceCache(
                                sku_id=sku,
                                region_name=region,
                                price=hourly_rate,
                                currency="USD"
                            )
                            db.add(new_cache)
                            db.commit()
                            db.close()
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[!] Real-time GCP pricing fetch failed: {e}")

        # --- FALLBACK CIRCUIT BREAKER ---
        if hourly_rate is None:
            sku_lower = sku.lower()
            hourly_rate = provider_fallbacks.get(sku_lower)
            
            if hourly_rate is None:
                # Substring/partial matching
                for fallback_key, price in provider_fallbacks.items():
                    if fallback_key in sku_lower or sku_lower in fallback_key:
                        hourly_rate = price
                        break

            if hourly_rate is None:
                # Semantic mapping based on component type and names
                comp_type = item.component_type.lower()
                generic_lower = item.generic_name.lower()
                
                if "compute" in comp_type or "vm" in sku_lower or "virtual machine" in generic_lower or "compute" in generic_lower or "server" in generic_lower:
                    if provider.lower() == "aws":
                        hourly_rate = 0.0416
                    elif provider.lower() == "gcp":
                        hourly_rate = 0.067
                    else:
                        hourly_rate = 0.096
                elif "db" in comp_type or "database" in comp_type or "db" in sku_lower or "database" in generic_lower or "sql" in generic_lower or "postgres" in generic_lower:
                    if provider.lower() == "aws":
                        hourly_rate = 0.08
                    elif provider.lower() == "gcp":
                        hourly_rate = 0.10
                    else:
                        hourly_rate = 0.130
                elif "storage" in comp_type or "store" in comp_type or "storage" in sku_lower or "blob" in generic_lower or "s3" in generic_lower or "bucket" in generic_lower or "disk" in generic_lower:
                    hourly_rate = 0.02
                elif "net" in comp_type or "network" in comp_type or "net" in sku_lower or "network" in generic_lower or "vpc" in generic_lower or "vnet" in generic_lower or "ip" in generic_lower:
                    hourly_rate = 0.005
                else:
                    hourly_rate = 0.05

        # Calculate standard cloud monthly operational hours (730 hours/month)
        monthly_cost = float(hourly_rate) * 730 * quantity
        total_monthly_cost += monthly_cost

        component_payload = item.model_dump()
        component_payload["calculated_monthly_cost"] = round(monthly_cost, 2)
        calculated_components.append(component_payload)

    return {
        "summary": blueprint_data.architecture_summary,
        "provider": provider.lower(),
        "region": region,
        "components": calculated_components,
        "total_monthly_cost_estimate": round(total_monthly_cost, 2),
        "security_warning": blueprint_data.security_warning,
    }
