from __future__ import annotations

import time

from google.adk import Event

from src.tools.monitor_pipeline import apply_pet_care_deltas
from src.workflow.context import StateBundle
from src.workflow.helpers import log_node, session_id


def pet_care_node(ctx, node_input: StateBundle) -> Event:
    started = time.perf_counter()
    care = apply_pet_care_deltas(
        node_input.user.user_id,
        node_input.user,
        node_input.pet,
        node_input.pending_exp,
        node_input.pending_stress,
        node_input.source,
    )

    log_node(
        session_id(ctx),
        node_input.user.user_id,
        "pet_care_node",
        started,
        route="end",
        payload={"mood": care.mood, "leveled_up": care.leveled_up, "evolved_to": care.evolved_to},
    )
    return Event(
        output={
            "care": care.model_dump(),
            "dashboard": node_input.dashboard.model_dump() if node_input.dashboard else None,
        }
    )
