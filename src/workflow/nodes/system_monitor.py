from __future__ import annotations

import time

from google.adk import Event

from src.tools.monitor_pipeline import (
    compute_exp_stress_deltas,
    persist_activity_log,
    snapshot_from_dict,
)
from src.tools.system_monitor import SystemMonitor
from src.workflow.context import InitResult, StateBundle
from src.workflow.helpers import log_node, session_id


def system_monitor_node(ctx, node_input: InitResult) -> Event:
    started = time.perf_counter()
    monitor = SystemMonitor.instance()
    monitor.start()
    snap_dict = monitor.get_snapshot_and_reset()

    snapshot = snapshot_from_dict(snap_dict)
    exp_gain, stress_delta = compute_exp_stress_deltas(snap_dict, snapshot)
    persist_activity_log(node_input.user.user_id, snapshot, exp_gain, stress_delta)

    log_node(
        session_id(ctx), node_input.user.user_id, "system_monitor_node", started,
        route="pet_care_node", payload={"exp_gain": exp_gain, "stress_delta": stress_delta},
    )
    return Event(
        output=StateBundle(
            user=node_input.user,
            pet=node_input.pet,
            snapshot=snapshot,
            pending_exp=exp_gain,
            pending_stress=stress_delta,
            source="monitor",
        )
    )
