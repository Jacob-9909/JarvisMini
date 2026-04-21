"""Smart Office Life Agent — ADK 2.0 Graph Workflow 조립."""

from __future__ import annotations

from google.adk import Workflow

from src.workflow.context import CURRENT_WORKFLOW_INPUT, WorkflowInput
from src.workflow.nodes import (
    dashboard_node,
    end_node,
    init_node,
    pet_care_node,
    router_node,
    system_monitor_node,
)

root_agent = Workflow(
    name="smart_office_workflow",
    edges=[
        ("START", init_node, router_node),
        (
            router_node,
            {
                "dashboard_node": dashboard_node,
                "system_monitor_node": system_monitor_node,
                "end": end_node,
            },
        ),
        (dashboard_node, pet_care_node),
        (system_monitor_node, pet_care_node),
        (pet_care_node, end_node),
    ],
)

__all__ = ["root_agent", "WorkflowInput", "CURRENT_WORKFLOW_INPUT"]
