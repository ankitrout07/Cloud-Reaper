"""
Natural Language Cost Query Interface

Conversational AI interface for natural language cost queries using
intent recognition, SQL generation, and context management.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from google import genai
from google.genai import types

from reaper.engine.models.resources import SessionLocal
from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)


class CostQueryInterface:
    """
    Conversational AI interface for natural language cost queries
    using intent recognition, SQL generation, and context management.
    """

    # Intent classification templates
    INTENT_CLASSES = {
        "cost_query": "Query current or historical costs",
        "comparison": "Compare costs between different dimensions",
        "forecast": "Predict future costs or resource needs",
        "optimization": "Request cost optimization recommendations",
        "anomaly_explanation": "Ask about cost anomalies or spikes",
        "resource_inventory": "Query about specific resources or services",
        "budget_status": "Check budget compliance and status",
        "recommendation": "Request actionable recommendations",
    }

    def __init__(self):
        """Initialize the cost query interface with Gemini client."""
        import os

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        self.client = genai.Client(api_key=api_key)
        self.model_identity = "gemini-2.5-flash"

        # Conversation context storage
        self.conversation_history: dict[str, list[dict]] = {}

    def classify_intent(self, query: str) -> dict[str, Any]:
        """
        Classify the user's query into intent categories using Gemini.

        Args:
            query: Natural language query from user

        Returns:
            Dictionary with intent classification and metadata
        """
        prompt = f"""
        Classify the following cloud cost query into one of these intent categories:
        {json.dumps(self.INTENT_CLASSES, indent=2)}

        Query: "{query}"

        Return a JSON object with:
        - intent: the primary intent category
        - confidence: confidence score (0-1)
        - entities: extracted entities (time_range, resource_type, provider, service, etc.)
        - original_query: the original query text
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_identity,
                contents=prompt,
                generation_config=types.GenerationConfig(
                    temperature=0.1, response_mime_type="application/json"
                ),
            )

            result = json.loads(response.text)
            logger.info(
                f"Intent classified: {result.get('intent')} with confidence {result.get('confidence')}"
            )
            return result

        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            # Fallback to rule-based classification
            return self._fallback_intent_classification(query)

    def _fallback_intent_classification(self, query: str) -> dict[str, Any]:
        """Rule-based fallback for intent classification."""
        query_lower = query.lower()

        # Simple keyword matching
        intent_patterns = {
            "cost_query": ["cost", "spend", "billing", "price", "how much"],
            "comparison": ["compare", "difference", "versus", "vs", "between"],
            "forecast": ["predict", "forecast", "project", "expect", "future"],
            "optimization": ["optimize", "reduce", "save", "cut", "cheaper"],
            "anomaly_explanation": ["why", "spike", "increase", "anomaly", "unusual"],
            "resource_inventory": ["list", "show", "resources", "instances", "vms"],
            "budget_status": ["budget", "limit", "threshold", "compliance"],
            "recommendation": ["recommend", "should", "suggest", "advice"],
        }

        # Find best matching intent
        best_intent = "cost_query"  # Default
        max_matches = 0

        for intent, patterns in intent_patterns.items():
            matches = sum(1 for pattern in patterns if pattern in query_lower)
            if matches > max_matches:
                max_matches = matches
                best_intent = intent

        return {
            "intent": best_intent,
            "confidence": 0.6,  # Lower confidence for rule-based
            "entities": self._extract_entities(query),
            "original_query": query,
        }

    def _extract_entities(self, query: str) -> dict[str, Any]:
        """Extract entities from the query using pattern matching."""
        entities = {}
        query_lower = query.lower()

        # Time range extraction
        time_patterns = {
            "today": (datetime.now().date(), datetime.now().date()),
            "yesterday": (
                datetime.now().date() - timedelta(days=1),
                datetime.now().date() - timedelta(days=1),
            ),
            "this week": (
                datetime.now().date() - timedelta(days=datetime.now().weekday()),
                datetime.now().date(),
            ),
            "this month": (
                datetime.now().date().replace(day=1),
                datetime.now().date(),
            ),
            "last month": (
                (datetime.now().date().replace(day=1) - timedelta(days=1)).replace(day=1),
                datetime.now().date().replace(day=1) - timedelta(days=1),
            ),
        }

        for time_phrase, (start, end) in time_patterns.items():
            if time_phrase in query_lower:
                entities["time_range"] = {"start": start.isoformat(), "end": end.isoformat()}
                break

        # Provider extraction
        providers = ["azure", "aws", "gcp", "google cloud"]
        for provider in providers:
            if provider in query_lower:
                entities["provider"] = provider
                break

        # Resource type extraction
        resource_types = ["vm", "virtual machine", "storage", "database", "network", "function"]
        for resource_type in resource_types:
            if resource_type in query_lower:
                entities["resource_type"] = resource_type
                break

        return entities

    def generate_sql_query(self, intent_result: dict[str, Any]) -> tuple[str, dict]:
        """
        Generate SQL query based on intent classification and entities.

        Args:
            intent_result: Result from intent classification

        Returns:
            Tuple of (SQL query string, parameters dict)
        """
        intent = intent_result.get("intent")
        entities = intent_result.get("entities", {})

        base_query = ""
        params = {}

        if intent == "cost_query":
            base_query = """
                SELECT 
                    provider,
                    resource_type,
                    SUM(cost_amount) as total_cost,
                    COUNT(*) as resource_count
                FROM cost_history
                WHERE 1=1
            """
            if "time_range" in entities:
                base_query += " AND cost_date BETWEEN :start_date AND :end_date"
                params["start_date"] = entities["time_range"]["start"]
                params["end_date"] = entities["time_range"]["end"]
            if "provider" in entities:
                base_query += " AND provider = :provider"
                params["provider"] = entities["provider"]
            base_query += " GROUP BY provider, resource_type ORDER BY total_cost DESC"

        elif intent == "resource_inventory":
            base_query = """
                SELECT 
                    provider,
                    resource_type,
                    name,
                    region,
                    sku,
                    active,
                    hourly_rate
                FROM legacy_resources
                WHERE 1=1
            """
            if "provider" in entities:
                base_query += " AND provider = :provider"
                params["provider"] = entities["provider"]
            if "resource_type" in entities:
                base_query += " AND resource_type LIKE :resource_type"
                params["resource_type"] = f"%{entities['resource_type']}%"
            base_query += " ORDER BY provider, resource_type, name LIMIT 100"

        elif intent == "comparison":
            base_query = """
                SELECT 
                    provider,
                    resource_type,
                    SUM(cost_amount) as total_cost,
                    AVG(cost_amount) as avg_cost
                FROM cost_history
                WHERE 1=1
            """
            if "time_range" in entities:
                base_query += " AND cost_date BETWEEN :start_date AND :end_date"
                params["start_date"] = entities["time_range"]["start"]
                params["end_date"] = entities["time_range"]["end"]
            base_query += " GROUP BY provider, resource_type ORDER BY total_cost DESC"

        else:
            # Default generic query
            base_query = """
                SELECT 
                    provider,
                    resource_type,
                    COUNT(*) as count,
                    SUM(hourly_rate) as estimated_hourly_cost
                FROM legacy_resources
                WHERE active = 1
                GROUP BY provider, resource_type
                ORDER BY estimated_hourly_cost DESC
            """

        return base_query, params

    def execute_query(self, sql: str, params: dict) -> list[dict]:
        """Execute the generated SQL query and return results."""
        try:
            db = SessionLocal()
            result = db.execute(sql, params)
            columns = result.keys()
            rows = result.fetchall()

            results = [dict(zip(columns, row)) for row in rows]
            db.close()
            return results

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return []

    def generate_response(
        self, query: str, query_results: list[dict], intent_result: dict[str, Any]
    ) -> str:
        """
        Generate natural language response using Gemini based on query results.

        Args:
            query: Original user query
            query_results: Results from SQL query execution
            intent_result: Intent classification result

        Returns:
            Natural language response string
        """
        prompt = f"""
        You are a cloud cost management assistant. Answer the user's question based on the query results.

        User Query: "{query}"
        Intent: {intent_result.get("intent")}
        Entities: {json.dumps(intent_result.get("entities", {}))}

        Query Results:
        {json.dumps(query_results, indent=2, default=str)}

        Provide a helpful, conversational response that:
        1. Directly answers the user's question
        2. Highlights key insights from the data
        3. Provides context and recommendations when appropriate
        4. Uses proper formatting for numbers and dates
        5. Suggests follow-up questions if relevant

        Keep the response concise but informative.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_identity,
                contents=prompt,
                generation_config=types.GenerationConfig(temperature=0.7),
            )

            return response.text

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return self._fallback_response(query, query_results, intent_result)

    def _fallback_response(
        self, query: str, query_results: list[dict], intent_result: dict[str, Any]
    ) -> str:
        """Fallback response generation without AI."""
        if not query_results:
            return f"I couldn't find any data to answer your question about '{query}'."

        intent = intent_result.get("intent")

        if intent == "cost_query":
            total_cost = sum(r.get("total_cost", 0) for r in query_results)
            return f"Based on the data, the total cost is ${total_cost:.2f} across {len(query_results)} resource categories."

        if intent == "resource_inventory":
            count = len(query_results)
            return f"Found {count} resources matching your criteria."

        if intent == "comparison":
            providers = set(r.get("provider") for r in query_results)
            return f"Cost comparison across {len(providers)} providers: {', '.join(providers)}"

        return f"Found {len(query_results)} results related to your query."

    def process_query(self, query: str, session_id: str = "default") -> dict[str, Any]:
        """
        Main method to process a natural language query end-to-end.

        Args:
            query: Natural language query from user
            session_id: Session identifier for conversation context

        Returns:
            Dictionary with response and metadata
        """
        start_time = datetime.now()

        # Initialize conversation history if needed
        if session_id not in self.conversation_history:
            self.conversation_history[session_id] = []

        try:
            # Step 1: Classify intent
            intent_result = self.classify_intent(query)

            # Step 2: Generate SQL query
            sql, params = self.generate_sql_query(intent_result)

            # Step 3: Execute query
            query_results = self.execute_query(sql, params)

            # Step 4: Generate response
            response_text = self.generate_response(query, query_results, intent_result)

            # Step 5: Store in conversation history
            self.conversation_history[session_id].append(
                {
                    "query": query,
                    "intent": intent_result.get("intent"),
                    "response": response_text,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            processing_time = (datetime.now() - start_time).total_seconds()

            return {
                "success": True,
                "response": response_text,
                "intent": intent_result.get("intent"),
                "entities": intent_result.get("entities"),
                "query_results": query_results,
                "processing_time": processing_time,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def get_conversation_history(self, session_id: str) -> list[dict]:
        """Get conversation history for a session."""
        return self.conversation_history.get(session_id, [])

    def clear_conversation_history(self, session_id: str) -> None:
        """Clear conversation history for a session."""
        if session_id in self.conversation_history:
            del self.conversation_history[session_id]
