# Audit Logs & Change Tracking

To maintain operational integrity and strict regulatory compliance across your cloud deployments, Cloud-Reaper includes a high-fidelity, comprehensive Audit Logging system. In cloud financial management (FinOps), tracking who changed what, when, and why is critical for maintaining **cost attribution stability** and preventing untracked budget leaks.

This document details the architecture, data structures, and usage of Cloud-Reaper's change tracking engine for Cost Reports, Virtual Tags, and Business Segments.

---

## Why FinOps Auditing Matters

Cloud cost attribution is dynamic. A single modification to a virtual tag allocation or a business segment boundary can instantly reclassify millions of dollars of cloud spend. Without transactional auditing, organizations face:
- **Attribution Drift**: Sudden shifts in cost centers due to unlogged rule changes.
- **Reporting Discrepancies**: Historical cost reports changing retroactively without explanation.
- **Security Vulnerabilities**: Unauthorized changes to business units, budgets, or report scopes.

To prevent this, Cloud-Reaper enforces a continuous audit pipeline capturing every configuration state transition.

---

## Mathematical Formalization of Attribution Stability

To quantify the impact of tag and segment modifications, the Audit Engine calculates the **Attribution Stability Index (ASI)** over a transition period $t \to t'$. If a modification changes the cost assignment of resources across $N$ segments, the ASI is given by:

$$\text{ASI} = 100 \times \left( \frac{\sum_{i=1}^{N} \min(\text{Cost}_i(t), \text{Cost}_i(t'))}{\sum_{i=1}^{N} \max(\text{Cost}_i(t), \text{Cost}_i(t'))} \right)$$

If $\text{ASI} < 90\%$, the Audit Engine triggers a **High Drift Alert** in the Slack and Discord channels, warning cost center owners that a configuration change has drastically altered the cost model.

---

## Core Entities Tracked

The audit engine tracks configuration updates across three primary architectural pillars:

### 1. Cost Reports
Cost Reports define how telemetry queries parse, filter, and group billing items. Tracked actions include:
- **Filter Mutation**: Modification of PromQL query parameters or subscription inclusion sets.
- **Dashboard Pinning**: Adding or removing reports from high-visibility executive views.
- **Notification Updates**: Edits to recipients or threshold rules for report notifications.

### 2. Virtual Tags (Logical Taxonomies)
Virtual Tags allow logical grouping of assets without mutating physical cloud resources. Tracked actions include:
- **Precedence Rule Overrides**: Adjustments to the priority stack (e.g. prioritizing `CostCenter` over `Owner`).
- **Rule Mutations**: Changing the regular expression or string match rules used for tag normalization.
- **Unallocated Classifications**: Manual changes to the default fallback assignment taxonomy.

### 3. Segments (Organizational Units)
Segments bound departments, teams, and products to their respective financial scopes. Tracked actions include:
- **Ownership Changes**: Assigning new administrators or email channels to a team segment.
- **Resource Reallocations**: Moving a cloud account or tag boundary between segments.
- **Budget Threshold Mutations**: Adjusting warning or critical envelope settings for budgets.

---

## Architectural Data Flow

The flow of change tracking proceeds from UI/CLI trigger to PostgreSQL logging and RAG ingestion:

```
[ User Interaction ] ──> [ Flask Controllers ] ──> [ Session Context Manager ]
                                                            │
                                                            ▼
[ RAG Vector Index ] <── [ BM25 / RRF Sync ] <── [ ActionLog DB Model ]
```

Every state change executes within a transaction that writes directly to the local database, ensuring complete persistence before returning a success signal to the user interface.

---

## Persistence Schema & API Structures

All changes are logged in the `action_logs` relational table. The data shape for a logged modification is structured as follows:

```json
{
  "id": 2045,
  "resource_id": "config/virtual-tags/rules",
  "action_type": "RULE_MUTATE",
  "status": "SUCCESS",
  "details": "User updated rule for 'Production' environment. Normalization pattern updated from '*prod*' to '*(prod|production|prd)*'.",
  "timestamp": "2026-05-20T20:56:00Z"
}
```

### REST API Reference

The Cloud-Reaper API exposes endpoints to query and review auditing logs:

- `GET /api/activity`: Retrieve the last 10 audit trails from the database.
- `GET /api/v1/audit/search?query=<search_term>`: Full-text semantic search of audit event records.
- `POST /api/v1/audit/export`: Generate a cryptographically signed CSV or PDF audit compliance document.

---

## Using the Search Portal to Query Audits

Using the **System Documentation Portal** and the integrated **RAG Vector Search Bar**, engineers can search for audit event rules and architectural behaviors using natural language queries:

- *"How do I track virtual tag changes?"*
- *"Where are segment edits logged?"*
- *"Show me how cost report edits affect budget performance."*

The semantic parser will immediately highlight the relevant operational standards and return contextualized guidelines.
