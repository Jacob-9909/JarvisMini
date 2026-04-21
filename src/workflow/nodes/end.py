from __future__ import annotations

import logging
from typing import Any

from google.adk import Event

logger = logging.getLogger(__name__)


def end_node(ctx, node_input: Any) -> Event:
    logger.debug("--- END NODE ---")
    return Event(message="ok")
