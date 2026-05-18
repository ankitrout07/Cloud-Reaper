from reaper.engine.workload import PredictiveScalingEngine, SpotAdvisor, WorkloadPersonality


def test_workload_personality_stable():
    history = [20] * 50
    analyzer = WorkloadPersonality(period=10)
    result = analyzer.analyze(history)
    assert result["personality"] == "Stable"


def test_workload_personality_cyclic():
    # Create a strong cyclic pattern
    base = [10, 10, 80, 80, 10, 10]
    history = base * 10
    analyzer = WorkloadPersonality(period=6)
    result = analyzer.analyze(history)
    assert result["personality"] == "Cyclic/Periodic"
    assert "Burstable" in result["recommendation"]


def test_predictive_scaling_prewarm():
    # Rapidly increasing trend
    history = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
    scaler = PredictiveScalingEngine(forecast_steps=5)
    result = scaler.predict_load(history)
    assert result["action"] == "PRE_WARM"


def test_predictive_scaling_stay():
    history = [30, 32, 31, 29, 30, 31, 30, 32, 31, 29]
    scaler = PredictiveScalingEngine(forecast_steps=5)
    result = scaler.predict_load(history)
    assert result["action"] == "STAY"


def test_spot_advisor_risk():
    advisor = SpotAdvisor()
    # Risk should be higher in more volatile regions
    risk_low = advisor.get_interruption_risk("Standard_D2s_v3", "eastus")
    risk_high = advisor.get_interruption_risk("Standard_D2s_v3", "brazilsouth")

    # Extract numeric values for comparison
    prob_low = int(risk_low["interruption_probability"].replace("%", ""))
    prob_high = int(risk_high["interruption_probability"].replace("%", ""))

    assert prob_high > prob_low
