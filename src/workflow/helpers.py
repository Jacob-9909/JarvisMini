from __future__ import annotations

import logging
import time
from typing import Optional

from src.db.models import NodeExecution, User, PetProfile
from src.db.session import SessionLocal
from src.tools.pet import pick_species_for

logger = logging.getLogger(__name__)


def log_node(
    session_id: str,
    user_id: Optional[int],
    node: str,
    started: float,
    route: Optional[str] = None,
    payload: Optional[dict] = None,
    status: str = "ok",
) -> None:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    try:
        db = SessionLocal()
        db.add(
            NodeExecution(
                session_id=session_id,
                user_id=user_id,
                node_name=node,
                elapsed_ms=elapsed_ms,
                route=route,
                status=status,
                payload=payload or {},
            )
        )
        db.commit()
        db.close()
    except Exception as e:  # noqa: BLE001
        logger.debug("node_execution log failed: %s", e)


def session_id(ctx) -> str:
    return getattr(ctx, "session_id", None) or getattr(ctx, "id", None) or "ad-hoc"


def ensure_pet_profile(db, user_id: int, user: User) -> PetProfile:
    pet = db.query(PetProfile).filter(PetProfile.user_id == user_id).first()
    if pet:
        return pet
    species = pick_species_for(user.job_role, user.dev_tendency)
    pet = PetProfile(
        user_id=user_id,
        species=species,
        nickname=user.display_name or user.username,
        level=1,
        exp=0,
        mood="neutral",
        stress=0,
    )
    db.add(pet)
    db.commit()
    db.refresh(pet)
    return pet
