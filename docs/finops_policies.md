# FinOps Intelligence and Optimization Policies

This document outlines the core optimization and predictive intelligence algorithms running within the **Cloud-Reaper** FinOps layer.

## Q-Learning VM Right-Sizing

To prevent dangerous service degradation during automated downscaling, Cloud-Reaper utilizes an active **Q-learning reinforcement learning agent**:
- **States ($S$)**: Combination of active CPU utilization bands (0-10%, 10-30%, 30-70%, 70-100%) and RAM headroom metrics.
- **Actions ($A$)**: `KEEP_SKU`, `DOWNSIZE_FAMILY`, `UPGRADE_FAMILY`, or `HIBERNATE`.
- **Rewards ($R$)**: Structured as a balance between financial savings (lower instance costs) and SLA penalties (negative reward spikes when utilization breaches the critical 90% threshold).

Over several operational iterations, the agent learns the optimal policy ($\pi^*$) to downgrade underutilized compute pools without impacting performance.

## Workload Forecasting & Anomalies

We employ statistical time-series models to predict resource utilization trends:
- **ARIMA Predictive Engine**: Fits structural trend parameters on CPU/Memory histories to anticipate upcoming workload spikes, allowing pre-emptive auto-scaling.
- **Seasonal Decomposition Anomaly Detection**: Isolates raw usage from daily/weekly seasonal variations to detect underlying underutilization, flagging instances with consistent idle compute.

## Compliance Tagging Governance

Cloud-Reaper evaluates asset metadata tables against target tagging rules (e.g. `Owner`, `Environment`, `CostCenter`). Non-compliant assets are flagged as **Untagged Cost Sinks** and highlighted in report updates.
