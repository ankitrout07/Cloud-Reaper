package ml

import (
	"math"
	"math/rand"
	"sync"
	"time"
)

// RightsizingAgent implements Q-learning for workload rightsizing decisions
type RightsizingAgent struct {
	// Q-learning parameters
	learningRate    float64
	discountFactor  float64
	explorationRate float64

	// Environment type
	environmentType string

	// Q-table: state -> action values
	qTable   map[string][]float64
	qTableMu sync.RWMutex

	// Action space
	actions []string

	// Risk thresholds based on environment
	riskThresholds map[string]float64
}

// State represents the discretized state space
type State struct {
	CPU  int
	Mem  int
	IOPS int
	Net  int
}

// Action represents the possible actions
const (
	ActionStay          = "stay"
	ActionDownscale     = "downscale"
	ActionUpscale       = "upscale"
	ActionMigrateFamily = "migrate_family"
)

// NewRightsizingAgent creates a new rightsizing agent
func NewRightsizingAgent(environmentType string) *RightsizingAgent {
	ra := &RightsizingAgent{
		learningRate:    0.1,
		discountFactor:  0.9,
		explorationRate: 1.0,
		environmentType: environmentType,
		qTable:          make(map[string][]float64),
		actions:         []string{ActionStay, ActionDownscale, ActionUpscale, ActionMigrateFamily},
		riskThresholds:  make(map[string]float64),
	}

	ra.setRiskThresholds()
	return ra
}

// setRiskThresholds sets environment-aware risk thresholds
func (ra *RightsizingAgent) setRiskThresholds() {
	if ra.environmentType == "production" {
		ra.riskThresholds = map[string]float64{
			"high_utilization":   80.0,
			"medium_utilization": 60.0,
			"low_utilization":    30.0,
		}
	} else {
		// dev-test - more aggressive
		ra.riskThresholds = map[string]float64{
			"high_utilization":   70.0,
			"medium_utilization": 50.0,
			"low_utilization":    20.0,
		}
	}
}

// GetState discretizes continuous metrics into discrete states
func (ra *RightsizingAgent) GetState(cpu, mem, iops, net float64) State {
	discretize := func(val float64) int {
		if val < ra.riskThresholds["low_utilization"] {
			return 0
		}
		if val < ra.riskThresholds["medium_utilization"] {
			return 1
		}
		return 2
	}

	return State{
		CPU:  discretize(cpu),
		Mem:  discretize(mem),
		IOPS: discretize(iops),
		Net:  discretize(net),
	}
}

// stateKey converts state to string key for Q-table lookup
func (ra *RightsizingAgent) stateKey(state State) string {
	return string(rune(state.CPU)) + "," + string(rune(state.Mem)) + "," +
		string(rune(state.IOPS)) + "," + string(rune(state.Net))
}

// ChooseAction selects an action using epsilon-greedy policy
func (ra *RightsizingAgent) ChooseAction(state State) int {
	key := ra.stateKey(state)

	ra.qTableMu.Lock()
	if _, exists := ra.qTable[key]; !exists {
		ra.qTable[key] = make([]float64, len(ra.actions))
	}
	qValues := ra.qTable[key]
	ra.qTableMu.Unlock()

	// Epsilon-greedy exploration
	if rand.Float64() < ra.explorationRate {
		return rand.Intn(len(ra.actions))
	}

	// Choose best action
	bestAction := 0
	bestValue := qValues[0]
	for i, value := range qValues {
		if value > bestValue {
			bestValue = value
			bestAction = i
		}
	}

	return bestAction
}

// Learn updates Q-values using Q-learning update rule
func (ra *RightsizingAgent) Learn(state State, action int, reward float64, nextState State) {
	stateKey := ra.stateKey(state)
	nextStateKey := ra.stateKey(nextState)

	ra.qTableMu.Lock()
	defer ra.qTableMu.Unlock()

	// Initialize Q-values if needed
	if _, exists := ra.qTable[stateKey]; !exists {
		ra.qTable[stateKey] = make([]float64, len(ra.actions))
	}
	if _, exists := ra.qTable[nextStateKey]; !exists {
		ra.qTable[nextStateKey] = make([]float64, len(ra.actions))
	}

	currentQ := ra.qTable[stateKey][action]
	maxNextQ := 0.0
	for _, value := range ra.qTable[nextStateKey] {
		if value > maxNextQ {
			maxNextQ = value
		}
	}

	// Q-learning update: Q(s,a) = Q(s,a) + α * (reward + γ * max(Q(s',a')) - Q(s,a))
	newQ := currentQ + ra.learningRate*(reward+ra.discountFactor*maxNextQ-currentQ)
	ra.qTable[stateKey][action] = newQ
}

// EvaluateMigration evaluates safe down-scaling or cross-family migrations
func (ra *RightsizingAgent) EvaluateMigration(metrics map[string]float64, currentSKU string, environmentType string) map[string]interface{} {
	// Use provided environment type or fall back to instance setting
	env := environmentType
	if env == "" {
		env = ra.environmentType
	}

	// Set appropriate thresholds
	thresholds := ra.riskThresholds
	if env == "production" {
		thresholds = map[string]float64{
			"high_utilization":   80.0,
			"medium_utilization": 60.0,
			"low_utilization":    30.0,
		}
	} else {
		thresholds = map[string]float64{
			"high_utilization":   70.0,
			"medium_utilization": 50.0,
			"low_utilization":    20.0,
		}
	}

	cpuUtil := metrics["cpu"]
	memUtil := metrics["mem"]
	iops := metrics["iops"]
	net := metrics["net"]

	// Inference mode (exploit)
	ra.explorationRate = 0.0
	state := ra.GetState(cpuUtil, memUtil, iops, net)
	actionIdx := ra.ChooseAction(state)
	action := ra.actions[actionIdx]

	// Environment-aware risk assessment
	riskProfile := "Low"
	if action == ActionMigrateFamily {
		if memUtil > thresholds["high_utilization"] || cpuUtil > thresholds["high_utilization"] {
			riskProfile = "High"
		} else if memUtil > thresholds["medium_utilization"] || cpuUtil > thresholds["medium_utilization"] {
			riskProfile = "Medium"
		}
	} else if action == ActionDownscale {
		maxUtil := math.Max(cpuUtil, memUtil)
		if maxUtil > thresholds["medium_utilization"] {
			riskProfile = "Medium"
		}
		if maxUtil > thresholds["high_utilization"] {
			riskProfile = "High"
		}
	}

	// Production safety override
	if env == "production" && riskProfile == "High" {
		action = ActionStay
		riskProfile = "Low" // Override since we're staying
	}

	return map[string]interface{}{
		"recommended_action": action,
		"risk_profile":       riskProfile,
		"sla_maintained":     riskProfile != "High",
		"current_sku":        currentSKU,
		"environment_type":   env,
		"thresholds_used":    thresholds,
	}
}

// BatchEvaluateMigration performs batch evaluation for multiple instances
func (ra *RightsizingAgent) BatchEvaluateMigration(metricsList []map[string]float64, currentSKUs []string) []map[string]interface{} {
	results := make([]map[string]interface{}, len(metricsList))

	var wg sync.WaitGroup
	var resultsMu sync.Mutex
	
	for i, metrics := range metricsList {
		wg.Add(1)
		go func(idx int, m map[string]float64, sku string) {
			defer wg.Done()
			result := ra.EvaluateMigration(m, sku, "")
			
			// Protect results slice write with mutex
			resultsMu.Lock()
			results[idx] = result
			resultsMu.Unlock()
		}(i, metrics, currentSKUs[i])
	}

	wg.Wait()
	return results
}

// SetLearningRate sets the learning rate
func (ra *RightsizingAgent) SetLearningRate(rate float64) {
	ra.learningRate = rate
}

// SetDiscountFactor sets the discount factor
func (ra *RightsizingAgent) SetDiscountFactor(factor float64) {
	ra.discountFactor = factor
}

// SetExplorationRate sets the exploration rate
func (ra *RightsizingAgent) SetExplorationRate(rate float64) {
	ra.explorationRate = rate
}

// GetQTableSize returns the size of the Q-table
func (ra *RightsizingAgent) GetQTableSize() int {
	ra.qTableMu.RLock()
	defer ra.qTableMu.RUnlock()
	return len(ra.qTable)
}

// Reset resets the Q-table
func (ra *RightsizingAgent) Reset() {
	ra.qTableMu.Lock()
	defer ra.qTableMu.Unlock()
	ra.qTable = make(map[string][]float64)
}
