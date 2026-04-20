import asyncio
import logging
import os
from dotenv import load_dotenv

from src.workflow.agent import root_agent
from src.db.session import init_db, SessionLocal
from src.db.models import User, UserConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

async def run_workflow_for_user(user_id: int, max_retries: int, base_backoff: int):
    """Run ADK Workflow for a single user with Exponential Backoff"""
    logger.info(f"\n--- BATCH START [User {user_id}] ---")
    retries = 0
    success = False
    
    while retries <= max_retries and not success:
        try:
            # ADK Workflow execution manually via .arun
            events = []
            from google.adk import Runner
            from google.adk.sessions import InMemorySessionService
            runner = Runner(node=root_agent, session_service=InMemorySessionService(), auto_create_session=True)
            async for event in runner.run_async(user_id=str(user_id), session_id=f"batch_{user_id}", state_delta={"user_id": user_id}):
                # If it suspends (RequestInput)
                if getattr(event, 'instruction', None) or 'requestinput' in str(type(event)).lower():
                    logger.info(f"[User {user_id}] Workflow paused for HITL. Exiting batch gracefully.")
                    success = True
                    break
                    
            logger.info(f"[User {user_id}] Batch run completed cleanly.")
            success = True
        except Exception as e:
            logger.error(f"[User {user_id}] Error during batch execution: {e}")
            retries += 1
            if retries <= max_retries:
                wait_time = base_backoff ** retries
                logger.info(f"[User {user_id}] Exponential Backoff: sleeping {wait_time}s before retry #{retries}")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"[User {user_id}] Max retries exceeded. Giving up this batch.")

async def run_batch():
    init_db()
    
    interval = int(os.getenv("AGENT_INTERVAL_SECONDS", "300"))
    max_retries = int(os.getenv("MAX_RETRIES", "3"))
    base_backoff = 10  # starting seconds
    
    logger.info(f"Starting Multi-tenant BookChecker Scheduler. Interval: {interval}s")
    
    while True:
        db = SessionLocal()
        try:
            active_users = db.query(User).filter(User.is_active == True).all()
            user_ids = [u.id for u in active_users]
        except Exception as e:
            logger.error(f"Failed to fetch users: {e}")
            user_ids = []
        finally:
            db.close()
            
        if not user_ids:
            logger.warning("No active users found. Skipping this cycle.")
        else:
            logger.info(f"Processing users: {user_ids}")
            # Run all users concurrently
            tasks = [
                run_workflow_for_user(uid, max_retries, base_backoff) 
                for uid in user_ids
            ]
            await asyncio.gather(*tasks)

        logger.info(f"Global Batch finished. Sleeping {interval}s until next run...")
        await asyncio.sleep(interval)

def seed_test_user(channel_id: str = "mock_channel"):
    """CLI utility to inject a mock user for testing"""
    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "test_user").first()
        if not user:
            user = User(username="test_user", slack_channel_id=channel_id, is_active=True)
            db.add(user)
            db.flush() # Get user.id
            
            config = UserConfig(
                user_id=user.id,
                target_booking_url="https://yeyak.seoul.go.kr/web/search/selectPageListDetailSearchImg.do?code=T500&dCode=T502",
                target_user_id="seoul_id",
                target_user_password="seoul_pw",
                anniversary_date="2026-05-20",
                buffer_days=3,
                target_zone="A구역"
            )
            db.add(config)
            db.commit()
            print(f"✅ Test user seeded with ID: {user.id}, Channel: {channel_id}")
        else:
            # Update existing user channel if provided
            user.slack_channel_id = channel_id
            db.commit()
            print(f"✅ Updated existing test_user with channel: {channel_id}")
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--channel", type=str, default="mock_channel")
    args = parser.parse_args()
    
    if args.seed:
        seed_test_user(args.channel)
    else:
        try:
            asyncio.run(run_batch())
        except KeyboardInterrupt:
            logger.info("Scheduler manually stopped.")
