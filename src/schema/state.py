from typing import TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel

class SlotInfo(BaseModel):
    date: str
    zone: str
    available: bool
    price: Optional[str] = None
    url: Optional[str] = None

class AgentState(TypedDict):
    # Session
    session_info: Dict[str, Any]      # Cookies, login status, etc.
    target_site: str                  # Current URL being scanned
    
    # Results
    scan_results: List[SlotInfo]      # Raw results from crawler
    
    # Matching
    match_score: int                  # Score of the matched result (e.g. 100 for exact match)
    best_match: Optional[SlotInfo]    # The slot selected for booking
    
    # HITL (Human-in-the-loop)
    pending_action: Optional[str]     # e.g., "confirm_booking", "captcha_required"
    user_decision: Optional[str]      # e.g., "approve", "reject"
    
    # Meta
    retry_count: int
    error_msg: Optional[str]
