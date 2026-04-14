from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChargingStrategy = Literal["optimal_station", "nearest_station"]


@dataclass(slots=True)
class SimulationConfig:
    """Runtime configuration for the simulation environment."""

    time_step: int = 1
    end_time: int = 240

    low_battery_ratio: float = 0.2
    charge_to_ratio: float = 0.9
    safety_energy_margin: float = 0.0
    auto_return_to_depot: bool = True

    charge_queue_weight: float = 2.5
    charge_occupied_weight: float = 1.5
    charging_strategy: ChargingStrategy = "optimal_station"

    reward_base: float = 100.0
    distance_penalty: float = 0.6
    wait_time_penalty: float = 0.2
    overdue_penalty: float = 60.0

    enable_collaborative_tasks: bool = True
    auto_collaborative_dispatch: bool = True
    collaborative_partial_credit: bool = True
    collaborative_partial_credit_ratio: float = 0.5


@dataclass(slots=True)
class ScenarioConfig:
    """High-level scenario settings for map/task/entity generation."""

    num_vehicles: int
    num_tasks: int
    num_stations: int
    num_road_nodes: int
    map_width: float
    map_height: float
    horizon: int

    vehicle_battery_capacity: float = 120.0
    vehicle_load_capacity: float = 80.0
    vehicle_speed: float = 1.5
    vehicle_energy_per_km: float = 1.0

    task_max_weight: float = 30.0
    task_ttl_min: int = 25
    task_ttl_max: int = 80
    collaborative_task_ratio: float = 0.0
    collaborative_weight_min_scale: float = 1.1
    collaborative_weight_max_scale: float = 1.6

    station_num_piles: int = 2
    station_charge_rate: float = 6.0

    random_seed: int = 7


def preset_scenario(name: str) -> ScenarioConfig:
    presets = {
        "small": ScenarioConfig(
            num_vehicles=5,
            num_tasks=30,
            num_stations=2,
            num_road_nodes=25,
            map_width=30,
            map_height=30,
            horizon=180,
        ),
        "medium": ScenarioConfig(
            num_vehicles=10,
            num_tasks=100,
            num_stations=4,
            num_road_nodes=60,
            map_width=50,
            map_height=50,
            horizon=300,
        ),
        "large": ScenarioConfig(
            num_vehicles=20,
            num_tasks=300,
            num_stations=8,
            num_road_nodes=120,
            map_width=80,
            map_height=80,
            horizon=480,
            station_num_piles=3,
        ),
    }
    if name not in presets:
        raise ValueError(f"Unknown preset '{name}', choose from {sorted(presets)}")
    return presets[name]
