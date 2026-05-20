# Telemetry Ingestion and Metric Specifications

This spec details the Prometheus PromQL metric collectors and cost-to-telemetry cross-reference calculations driving the **Cloud-Reaper** dynamic waste indices.

## PromQL Telemetry Queries

To measure precise fleet performance, the collection engine executes asynchronous HTTP range queries against standard Prometheus instances.

### CPU Fleet Utilization Query

```promql
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode='idle'}[7d])) * 100)
```

This returns the 7-day average non-idle CPU percentage across all registered telemetry nodes.

## Dynamic Waste Calculations

Commercial cloud monitors evaluate billing metrics statically. Cloud-Reaper calculates real-time **Financial Compute Waste** by combining resource unit pricing sheets with performance metrics over active windows ($T$):

$$\text{Waste Rate (\%)} = 100 \times \left( 1.0 - \frac{\frac{1}{T}\int_{0}^{T} \text{Metric}_{\text{actual}}(t) \, dt}{\text{Metric}_{\text{provisioned}}} \right)$$

### Underutilization Remediation Rule

If the 7-day average utilization of an VM instance falls below **10.0%**, Cloud-Reaper automatically registers a cost optimization recommendation:
1. Flags the resource as **UNDERUTILIZED_COMPUTE**.
2. Calculates **Monthly Waste Impact** (50.0% of the baseline monthly SKU price cache).
3. Assigns remediation action: `DOWNGRADE_SKU_FAMILY` or `HIBERNATE_WORKLOAD`.
