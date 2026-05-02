from __future__ import annotations

import csv
import json
from pathlib import Path

from .entities import ChargingStation, Task, Vehicle


class SimulationLogger:
    """Structured logs for visualization and report analysis."""

    def __init__(self) -> None:
        self.step_logs: list[dict] = []
        self.vehicle_logs: list[dict] = []
        self.task_logs: list[dict] = []
        self.station_logs: list[dict] = []
        self.events: list[dict] = []

    def log_event(self, time_now: int, event_type: str, payload: dict) -> None:
        self.events.append(
            {
                "time": time_now,
                "event_type": event_type,
                **payload,
            }
        )

    def log_task_event(self, time_now: int, task: Task, event_type: str) -> None:
        self.task_logs.append(
            {
                "time": time_now,
                "event_type": event_type,
                "task_id": task.id,
                "status": task.status.value,
                "release_time": task.release_time,
                "deadline": task.deadline,
                "origin_node": task.origin_node,
                "weight": task.weight,
                "collaborative": task.collaborative,
                "delivered_weight": round(task.delivered_weight, 4),
                "remaining_weight": round(task.remaining_weight, 4),
                "assigned_vehicles": dict(task.assigned_vehicles),
                "assigned_vehicle": task.assigned_vehicle,
                "assigned_time": task.assigned_time,
                "service_distance": round(task.service_distance, 4),
                "service_duration": task.service_duration,
                "complete_time": task.complete_time,
            }
        )

    def log_vehicle_event(self, time_now: int, vehicle: Vehicle, event_type: str) -> None:
        self.vehicle_logs.append(
            {
                "time": time_now,
                "event_type": event_type,
                "vehicle_id": vehicle.id,
                "node": vehicle.current_node,
                "battery": round(vehicle.battery, 4),
                "status": vehicle.status.value,
                "assigned_task": vehicle.assigned_task,
                "task_load": round(vehicle.task_load, 4),
                "target_station": vehicle.target_station,
                "total_distance": round(vehicle.total_distance, 4),
                "total_score": round(vehicle.total_score, 4),
            }
        )

    def log_station_step(self, time_now: int, station: ChargingStation) -> None:
        self.station_logs.append(
            {
                "time": time_now,
                "station_id": station.id,
                "node_id": station.node_id,
                "queue_length": station.queue_length,
                "occupied_piles": station.occupied_piles,
                "waiting_vehicles": list(station.queue),
                "charging_slots": list(station.charging_slots),
            }
        )

    def log_step_snapshot(
        self,
        time_now: int,
        vehicles: dict[int, Vehicle],
        tasks: dict[int, Task],
        stations: dict[int, ChargingStation],
        total_score: float,
    ) -> None:
        pending = sum(1 for t in tasks.values() if t.status.value == "pending")
        completed = sum(1 for t in tasks.values() if t.status.value == "completed")
        expired = sum(1 for t in tasks.values() if t.status.value == "expired")
        charging_queues = sum(s.queue_length for s in stations.values())

        self.step_logs.append(
            {
                "time": time_now,
                "total_score": round(total_score, 4),
                "pending_tasks": pending,
                "completed_tasks": completed,
                "expired_tasks": expired,
                "charging_queue_total": charging_queues,
                "avg_battery": round(
                    sum(v.battery for v in vehicles.values()) / max(len(vehicles), 1),
                    4,
                ),
            }
        )

        for vehicle in vehicles.values():
            self.log_vehicle_event(time_now, vehicle, "step")

        for station in stations.values():
            self.log_station_step(time_now, station)

    def export_json(self, output_dir: str | Path) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        self._write_json(out / "step_log.json", self.step_logs)
        self._write_json(out / "vehicle_log.json", self.vehicle_logs)
        self._write_json(out / "task_log.json", self.task_logs)
        self._write_json(out / "station_log.json", self.station_logs)
        self._write_json(out / "events.json", self.events)

    def export_csv(self, output_dir: str | Path) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        self._write_csv(out / "step_log.csv", self.step_logs)
        self._write_csv(out / "vehicle_log.csv", self.vehicle_logs)
        self._write_csv(out / "task_log.csv", self.task_logs)
        self._write_csv(out / "station_log.csv", self.station_logs)
        self._write_csv(out / "events.csv", self.events)

    def _write_json(self, path: Path, payload: list[dict]) -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _write_csv(self, path: Path, payload: list[dict]) -> None:
        if not payload:
            path.write_text("", encoding="utf-8")
            return

        # 收集所有可能的字段名（因为不同事件可能有不同字段）
        all_keys = set()
        for row in payload:
            all_keys.update(row.keys())
        
        keys = sorted(all_keys)
        
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(payload)
