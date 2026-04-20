import os
from typing import List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field
import logging

from google.adk import Event, Workflow
from google.adk.events import RequestInput
from google.adk.agents import Agent

from src.schema.state import SlotInfo
from src.tools.crawler import CampingCrawler
from src.tools.notifier import SlackNotifier
from src.db.session import SessionLocal
from src.db.models import User, UserConfig, ScanHistory, NotificationLog

logger = logging.getLogger(__name__)

# --- Models ---
class WorkflowInput(BaseModel):
    user_id: int

class InitResult(BaseModel):
    user_id: int
    target_site: str
    target_zone: str | None
    anniversary_date: str | None
    buffer_days: int

class AuthResult(BaseModel):
    user_id: int
    success: bool
    session_info: List[Dict[str, Any]] = Field(default_factory=list)
    error_msg: str = ""
    target_site: str

class ScanResult(BaseModel):
    user_id: int
    target_site: str
    slots: List[SlotInfo] = Field(default_factory=list)
    error_msg: str = ""

class MatchResult(BaseModel):
    user_id: int
    best_match: SlotInfo | None = None
    match_score: int = 0
    route: str = "end"

class MatchPrompt(BaseModel):
    user_id: int
    target_zone: str
    anniversary_date: str | None
    buffer_days: int
    notified_slots: List[str]
    available_slots: List[Dict[str, Any]]

class LlmMatchEvaluation(BaseModel):
    user_id: int
    best_match_date: str | None = Field(description="The date of the chosen slot")
    best_match_zone: str | None = Field(description="The zone of the chosen slot")
    best_match_price: str | None = Field(description="The price of the chosen slot")
    match_score: int = Field(description="100 if perfect match, 50 if good alternative, 0 if nothing fits")
    route: str = "human_input"

class UserDecision(BaseModel):
    user_id: int
    approve: bool = Field(description="True if user wants to book, False otherwise")

# --- LLM Agent Definition ---
match_eval_agent = Agent(
    name="match_eval_agent",
    model=os.environ.get("MODEL", "gemini-2.5-flash"),
    instruction="""You are an intelligent camping reservation assistant.
Your goal is to evaluate available camping slots based on the user's preferences.
You will receive JSON containing user_id, target_zone, anniversary_date, buffer_days, a list of previously notified slots (which must NOT be chosen again), and available_slots.
Rules:
1. Ignore any slot whose 'date-zone' combination exists in notified_slots.
2. If there's an available slot matching the target_zone AND within +/- buffer_days of anniversary_date, prioritize it (score 100).
3. If no perfect match exists, but other available slots (diff zone or diff date) exist, pick one as an alternative (score 50).
4. If no slots are available, return score 0 and null for best_match fields.
Always return user_id exactly as input. You must output cleanly conforming to the output schema.
""",
    output_schema=LlmMatchEvaluation
)

# --- Helpers ---
def _is_within_anniversary_buffer(candidate_date_str: str, d_day_str: str, buffer_days: int) -> bool:
    if not candidate_date_str or not d_day_str: 
        return False
    try:
        candidate_date = datetime.strptime(candidate_date_str, "%Y-%m-%d")
        d_day = datetime.strptime(d_day_str, "%Y-%m-%d")
        delta = abs((candidate_date - d_day).days)
        return delta <= buffer_days
    except ValueError:
        return False

# --- Nodes ---
def init_node(ctx, node_input: WorkflowInput | dict | None = None) -> Event:
    # Primary: ctx.user_id is set by Runner.run_async(user_id=...)
    # Fallback: node_input for ADK Web UI usage
    try:
        user_id = int(ctx.user_id)
    except (AttributeError, TypeError, ValueError):
        user_id = 0
    if node_input is not None:
        if isinstance(node_input, WorkflowInput):
            user_id = node_input.user_id
        elif isinstance(node_input, dict) and "user_id" in node_input:
            user_id = int(node_input["user_id"])
    logger.info(f"[User {user_id}] --- INIT NODE ---")
    
    db = SessionLocal()
    try:
        config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
        if not config:
            logger.error(f"[User {user_id}] Config not found.")
            return Event(route=["end"], output=InitResult(user_id=user_id, target_site="", target_zone=None, anniversary_date=None, buffer_days=0))
            
        return Event(output=InitResult(
            user_id=user_id,
            target_site=config.target_booking_url,
            target_zone=config.target_zone,
            anniversary_date=config.anniversary_date,
            buffer_days=config.buffer_days or 3
        ))
    finally:
        db.close()

async def auth_node(ctx, node_input: InitResult) -> Event:
    logger.info(f"[User {node_input.user_id}] --- AUTH NODE ---")
    if not node_input.target_site:
        return Event(output=AuthResult(user_id=node_input.user_id, success=False, error_msg="No target site", target_site=""))

    db = SessionLocal()
    credentials = None
    try:
        config = db.query(UserConfig).filter(UserConfig.user_id == node_input.user_id).first()
        credentials = {"id": config.target_user_id, "pw": config.target_user_password}
    finally:
        db.close()

    crawler = CampingCrawler(headless=True)
    await crawler.initialize()
    
    try:
        login_result = await crawler.login(node_input.target_site, credentials)
        if login_result["status"] == "success":
            return Event(output=AuthResult(
                user_id=node_input.user_id,
                success=True,
                session_info=login_result.get("cookies", []),
                target_site=node_input.target_site
            ))
        else:
            return Event(output=AuthResult(
                user_id=node_input.user_id,
                success=False,
                error_msg=login_result.get("message", "unknown error"),
                target_site=node_input.target_site
            ))
    finally:
        await crawler.close()

def auth_router(ctx, node_input: InitResult | AuthResult) -> Event:
    # Handle if init failed
    if isinstance(node_input, InitResult):
        return Event(route=["end"])
    if not node_input.success:
        return Event(route=["end"])
    return Event(route=["scan_node"])

async def scan_node(ctx, node_input: AuthResult) -> Event:
    logger.info(f"[User {node_input.user_id}] --- SCAN NODE ---")
    crawler = CampingCrawler(headless=True)
    await crawler.initialize()
    
    try:
        # Pass cookies for session persistence
        slots = await crawler.scan_availability(node_input.target_site, session_info=node_input.session_info)
        
        db = SessionLocal()
        try:
            history = ScanHistory(
                user_id=node_input.user_id,
                target_site=node_input.target_site,
                found_slots=[s.model_dump() for s in slots if s.available]
            )
            db.add(history)
            db.commit()
        except Exception as e:
            logger.error(f"[User {node_input.user_id}] Failed to log ScanHistory to DB: {e}")
        finally:
            db.close()
            
        return Event(output=ScanResult(user_id=node_input.user_id, target_site=node_input.target_site, slots=slots))
    except Exception as e:
        return Event(output=ScanResult(user_id=node_input.user_id, target_site=node_input.target_site, error_msg=str(e)))
    finally:
        await crawler.close()

def match_shortcut_router(ctx, node_input: ScanResult) -> Event:
    """Check if there's an APPROVED slot before going to LLM"""
    logger.info(f"[User {node_input.user_id}] --- MATCH SHORTCUT ROUTER ---")
    
    db = SessionLocal()
    try:
        # Check for APPROVED slot
        approved_log = db.query(NotificationLog).filter(
            NotificationLog.user_id == node_input.user_id, 
            NotificationLog.status == "APPROVED"
        ).order_by(NotificationLog.notified_at.desc()).first()
        
        if approved_log:
            logger.info(f"[User {node_input.user_id}] Found an externally APPROVED slot: {approved_log.slot_id}")
            parts = approved_log.slot_id.rsplit("-", 1)
            best_match = SlotInfo(date=parts[0], zone=parts[1], available=True, price="", url="")
            return Event(route=["action_node"], output=MatchResult(user_id=node_input.user_id, best_match=best_match, match_score=100, route="action_node"))
            
        return Event(route=["llm_match_flow"])
    finally:
        db.close()

def prepare_match_prompt(ctx, node_input: ScanResult) -> MatchPrompt:
    logger.info(f"[User {node_input.user_id}] --- PREPARE LLM MATCH PROMPT ---")
    if node_input.error_msg or not node_input.slots:
        return MatchPrompt(user_id=node_input.user_id, target_zone="", anniversary_date=None, buffer_days=0, notified_slots=[], available_slots=[])
        
    db = SessionLocal()
    try:
        config = db.query(UserConfig).filter(UserConfig.user_id == node_input.user_id).first()
        anniversary = config.anniversary_date
        buffer_days = config.buffer_days or 3
        target_zone = config.target_zone or "A구역"
        
        # Avoid repeats
        logs = db.query(NotificationLog).filter(
            NotificationLog.user_id == node_input.user_id, 
            NotificationLog.status.in_(["SUCCESS", "PENDING", "APPROVED", "CANCELLED"])
        ).all()
        notified_slots = [log.slot_id for log in logs]
    finally:
        db.close()
    
    available_dicts = [s.model_dump() for s in node_input.slots if s.available]
    
    return MatchPrompt(
        user_id=node_input.user_id,
        target_zone=target_zone,
        anniversary_date=anniversary,
        buffer_days=buffer_days,
        notified_slots=notified_slots,
        available_slots=available_dicts
    )

def llm_match_router(ctx, node_input: LlmMatchEvaluation) -> Event:
    logger.info(f"[User {node_input.user_id}] --- LLM MATCH ROUTER (Score: {node_input.match_score}) ---")
    
    if getattr(node_input, "match_score", 0) > 0 and getattr(node_input, "best_match_date", None):
        
        # Save PENDING log
        db = SessionLocal()
        try:
            config = db.query(UserConfig).filter(UserConfig.user_id == node_input.user_id).first()
            target_booking_url = config.target_booking_url if config else ""
            log = NotificationLog(
                user_id=node_input.user_id,
                site=target_booking_url,
                slot_id=f"{node_input.best_match_date}-{node_input.best_match_zone}",
                status="PENDING"
            )
            db.add(log)
            db.commit()
        except Exception as e:
            logger.error(f"[User {node_input.user_id}] Failed to write PENDING log: {e}")
        finally:
            db.close()

        best_match = SlotInfo(date=node_input.best_match_date, zone=node_input.best_match_zone, available=True, price=node_input.best_match_price or "", url="")
        return Event(route=["human_input"], output=MatchResult(user_id=node_input.user_id, best_match=best_match, match_score=node_input.match_score, route="human_input"))
    else:
        return Event(route=["end"], output=MatchResult(user_id=node_input.user_id, route="end"))

async def human_input_node(ctx, node_input: MatchResult):
    """HITL node: wait for user approval"""
    logger.info(f"[User {node_input.user_id}] --- HUMAN INPUT NODE ---")

    bm = node_input.best_match
    
    db = SessionLocal()
    slack_channel_id = None
    try:
        u = db.query(User).filter(User.id == node_input.user_id).first()
        if u:
            slack_channel_id = u.slack_channel_id
    finally:
        db.close()
        
    notifier = SlackNotifier()
    if slack_channel_id:
        logger.info(f"Notify user {node_input.user_id} on Slack: Found a slot: {bm.date} Zone {bm.zone}.")
        await notifier.send_message(slack_channel_id, f"🚨 Slot Found for User {node_input.user_id}!\nDate: {bm.date}\nZone: {bm.zone}\nPrice: {bm.price}")
    else:
        logger.warning(f"No slack_channel_id for user {node_input.user_id}, skipping message.")

    yield RequestInput(
        message=f"Found a slot: {bm.date} Zone {bm.zone}. Price: {bm.price}. Do you want to book?",
        response_schema=UserDecision,
        payload={"slot_info": bm.model_dump(), "user_id": node_input.user_id}
    )

async def action_node(ctx, node_input: Union[UserDecision, dict]) -> Event:
    user_id = getattr(node_input, 'user_id', node_input.get('user_id', 0)) if isinstance(node_input, dict) else getattr(node_input, 'user_id', 0)
    logger.info(f"[User {user_id}] --- ACTION NODE ---")
    
    approved = False
    
    if isinstance(node_input, dict):
        approved = node_input.get("approve", False)
    elif hasattr(node_input, "approve"):
        approved = node_input.approve
        
    status = "SUCCESS" if approved else "CANCELLED"
    
    db = SessionLocal()
    try:
        # Find the PENDING or APPROVED log to update
        log = db.query(NotificationLog).filter(
            NotificationLog.user_id == user_id, 
            NotificationLog.status.in_(["PENDING", "APPROVED"])
        ).order_by(NotificationLog.id.desc()).first()
        
        if log:
            slot_id = log.slot_id
            log.status = status
            db.commit()
            logger.info(f"[User {user_id}] Updated slot {log.slot_id} to {status}.")
        else:
            logger.warning(f"[User {user_id}] No matching PENDING/APPROVED slot found to update.")
            
        u = db.query(User).filter(User.id == user_id).first()
        slack_channel_id = u.slack_channel_id if u else None
            
    except Exception as e:
        logger.error(f"[User {user_id}] Failed to update notification: {e}")
        slack_channel_id = None
    finally:
        db.close()

    notifier = SlackNotifier()
    if approved:
        # Actually execute reservation click action using Crawler!
        crawler = CampingCrawler(headless=True)
        await crawler.initialize()
        try:
            # Re-fetch user credential and target site
            db = SessionLocal()
            u_config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
            creds = {"id": u_config.target_user_id, "pw": u_config.target_user_password} if u_config else {}
            db.close()
            
            # 1. Login
            await crawler.login(site, creds)
            
            # 2. Extract Date/Zone from slot_id, then Reserve
            # Format: YYYY-MM-DD-Zone
            parts = slot_id.rsplit("-", 1)
            target_date = parts[0] if len(parts) > 1 else ""
            target_zone = parts[1] if len(parts) > 1 else ""
            
            slot = SlotInfo(date=target_date, zone=target_zone, available=True, url=site)
            await crawler.hold_reservation(slot)
            
            if slack_channel_id:
                await notifier.send_message(slack_channel_id, f"✅ User {user_id}: Booking ({slot_id}) Successfully Held!")
        except Exception as e:
            logger.error(f"Failed during reservation hold: {e}")
            if slack_channel_id:
                await notifier.send_message(slack_channel_id, f"⚠️ User {user_id}: Booking Approved but failed on Site: {e}")
        finally:
            await crawler.close()
    else:
        if slack_channel_id:
            await notifier.send_message(slack_channel_id, f"❌ User {user_id}: Booking Cancelled by user.")

    return Event(message="Workflow complete.")

def end_node(ctx, node_input: Any) -> Event:
    logger.info(f"--- END NODE ---")
    return Event(message="ended")

root_agent = Workflow(
    name="bookchecker_workflow",
    edges=[
        ("START", init_node, auth_node, auth_router),
        (
            auth_router,
            {
                "scan_node": scan_node,
                "end": end_node
            }
        ),
        (scan_node, match_shortcut_router),
        (
            match_shortcut_router,
            {
                "action_node": action_node,
                "llm_match_flow": (prepare_match_prompt, match_eval_agent, llm_match_router)
            }
        ),
        (
            llm_match_router,
            {
                "human_input": human_input_node,
                "end": end_node
            }
        ),
        (human_input_node, action_node),
        (action_node, end_node),
    ]
)
