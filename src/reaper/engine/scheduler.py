from pathlib import Path

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from stable_baselines3 import PPO

# Constants
DEFAULT_NODE_COUNT = 5
MAX_NODE_COUNT = 20
MIN_NODE_COUNT = 1
JOB_POISSON_MEAN = 5
WAIT_PENALTY_WEIGHT = 0.1
LOW_DENSITY_THRESHOLD = 0.2


class BuildNodeEnv(gym.Env):
    """
    Custom Environment for Cloud-Reaper Build Node Scaling.
    Rewards fast builds, penalizes high idle-time costs.
    """

    def __init__(self):
        super().__init__()
        # Actions: 0=Scale Down, 1=Stay, 2=Scale Up
        self.action_space = spaces.Discrete(3)

        # Observation: [Current Node Count, Pending Job Count, Average Wait Time]
        self.observation_space = spaces.Box(
            low=np.array([1, 0, 0]), high=np.array([20, 100, 3600]), dtype=np.float32
        )

        self.state = np.array([DEFAULT_NODE_COUNT, 0, 0], dtype=np.float32)
        self.cost_per_node = 0.50  # $0.50/hr
        self.value_per_job = 2.0  # $2.00 value for fast completion

    def step(self, action):
        nodes, pending, _wait = self.state

        # Apply action
        if action == 0:
            nodes = max(MIN_NODE_COUNT, nodes - 1)
        if action == 2:
            nodes = min(MAX_NODE_COUNT, nodes + 1)

        # Simulate environment dynamics
        new_jobs = np.random.poisson(JOB_POISSON_MEAN)
        completed = min(pending + new_jobs, int(nodes * 2))
        new_pending = max(0, pending + new_jobs - completed)
        new_wait = (new_pending / nodes) * 60  # Simulated wait in seconds

        self.state = np.array([nodes, new_pending, new_wait], dtype=np.float32)

        # Reward function: Value from jobs - Cost of nodes - Penalty for wait
        reward = (
            (completed * self.value_per_job)
            - (nodes * self.cost_per_node)
            - (new_wait * WAIT_PENALTY_WEIGHT)
        )

        done = False
        truncated = False
        return self.state, reward, done, truncated, {}

    def reset(self, seed=None, options=None):  # noqa: ARG002
        super().reset(seed=seed)
        self.state = np.array([DEFAULT_NODE_COUNT, 0, 0], dtype=np.float32)
        return self.state, {}


class ReaperAgent:
    def __init__(self, model_path="data/reaper_agent.zip"):
        self.model_path = Path(model_path)
        self.env = BuildNodeEnv()
        self.model = self._load_or_train()

    def _load_or_train(self):
        if self.model_path.exists():
            return PPO.load(str(self.model_path), env=self.env)

        return PPO("MlpPolicy", self.env, verbose=1)

    def get_action(self, current_nodes, pending_jobs, avg_wait):
        obs = np.array([current_nodes, pending_jobs, avg_wait], dtype=np.float32)
        action, _states = self.model.predict(obs, deterministic=True)
        return action  # 0, 1, or 2


def suggest_k8s_consolidation(node_metrics):
    """
    MostAllocated Bin Packing Strategy Bridge.
    node_metrics: list of {node_name, cpu_allocated, mem_allocated, capacity}
    """
    # Sort nodes by utilization (ascending) to identify drain targets
    sorted_nodes = sorted(node_metrics, key=lambda x: x["cpu_allocated"] / x["capacity"]["cpu"])

    recommendations = []
    for node in sorted_nodes:
        utilization = node["cpu_allocated"] / node["capacity"]["cpu"]
        if utilization < LOW_DENSITY_THRESHOLD:
            reason = (
                f"Low density detected ({utilization * 100:.1f}%). "
                "MostAllocated strategy suggests consolidation."
            )
            recommendations.append(
                {
                    "target_node": node["node_name"],
                    "action": "DRAIN",
                    "reason": reason,
                    "potential_saving": 45.0,  # Mock monthly saving per node
                }
            )

    return recommendations
