import os
import sys
import logging
from pathlib import Path

# 프로젝트 루트 경로를 sys.path에 추가하여 ModuleNotFoundError 방지
root_dir = str(Path(__file__).parent.parent.parent)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

from src.db.session import SessionLocal
from src.db.models import NotificationLog, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def handle_interaction(ack, body, client):
    # Acknowledge the request immediately
    ack()
    
    actions = body.get("actions", [])
    if not actions:
        return
        
    action = actions[0]
    action_id = action.get("action_id")
    # Our action_id format is "approve_reservation_USERID" or "cancel_reservation_USERID"
    # But for now we just use a generic 'PENDING' tracker. 
    # In a more advanced setup, we'd encode the log_id in the button value.
    
    user_slack_id = body.get("user", {}).get("id")
    channel_id = body.get("container", {}).get("channel_id")
    
    db = SessionLocal()
    try:
        # Find the user by slack_channel_id or slack_id
        user = db.query(User).filter(User.slack_channel_id == channel_id).first()
        if not user:
            logger.warning(f"Could not find user for channel {channel_id}")
            return
            
        # Find the latest PENDING notification for this user
        log = db.query(NotificationLog).filter(
            NotificationLog.user_id == user.id,
            NotificationLog.status == "PENDING"
        ).order_by(NotificationLog.notified_at.desc()).first()
        
        if not log:
            logger.warning(f"No pending notification found for user {user.id}")
            return

        if action_id.startswith("approve"):
            log.status = "APPROVED"
            message = "✅ 승인이 완료되었습니다. 다음 스캔 주기에서 예약을 시도합니다!"
        else:
            log.status = "CANCELLED"
            message = "❌ 예약이 취소되었습니다."
            
        db.commit()
        
        # Update the original message to remove buttons and show status
        client.chat_update(
            channel=channel_id,
            ts=body.get("container", {}).get("message_ts"),
            text=message,
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message}
                }
            ]
        )
        logger.info(f"User {user.id} {log.status} slot {log.slot_id}")
        
    except Exception as e:
        logger.error(f"Error handling interaction: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    app_token = os.environ.get("SLACK_APP_TOKEN")
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    
    if not app_token or not bot_token:
        print("❌ SLACK_APP_TOKEN and SLACK_BOT_TOKEN required.")
        exit(1)
        
    app = App(token=bot_token)
    
    # Register for block_actions
    @app.action("approve_reservation_001")
    def handle_approve(ack, body, client):
        handle_interaction(ack, body, client)

    @app.action("cancel_reservation_001")
    def handle_cancel(ack, body, client):
        handle_interaction(ack, body, client)
    
    handler = SocketModeHandler(app, app_token)
    handler.start()
