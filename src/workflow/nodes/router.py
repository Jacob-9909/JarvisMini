from __future__ import annotations

import time

from google.adk import Event

from src.workflow.context import InitResult
from src.workflow.helpers import log_node, session_id


def router_node(ctx, node_input: InitResult) -> Event:
    started = time.perf_counter()
    action = (node_input.action or "status").lower()

    system_actions = {"monitor", "sample"}
    dashboard_actions = {"status", "bus", "cafe", "lunch_roulette", "calendar", "pet_interact"}

    if action in system_actions:
        route = "system_monitor_node"
    elif action in dashboard_actions:
        route = "dashboard_node"
    else:
        route = "end"

    log_node(session_id(ctx), node_input.user.user_id, "router_node", started, route=route, payload={"action": action})
    return Event(route=[route], output=node_input)
