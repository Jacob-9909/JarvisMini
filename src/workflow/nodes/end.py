from __future__ import annotations

import logging
from typing import Any

from google.adk import Event

logger = logging.getLogger(__name__)


def end_node(ctx, node_input: Any) -> Event:
    logger.debug("--- END NODE ---")
    if isinstance(node_input, dict):
        text = node_input.get("text")
        if text is not None and str(text).strip():
            return Event(message=str(text), output=node_input)
    return Event(output=node_input)
