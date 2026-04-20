import asyncio
import os
import sys
from pathlib import Path

# 프로젝트 루트 경로를 sys.path에 추가하여 ModuleNotFoundError 방지
root_dir = str(Path(__file__).parent.parent.parent)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from dotenv import load_dotenv
from src.tools.notifier import SlackNotifier

async def test_slack_notification(channel_id: str):
    load_dotenv()
    notifier = SlackNotifier()
    
    # 봇 토큰 확인 (실수 방지)
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        print("❌ .env 파일에 SLACK_BOT_TOKEN이 설정되어 있지 않습니다.")
        return

    # 채널 ID 형식 체크 (보통 C로 시작)
    if not channel_id.startswith("C") and not channel_id.startswith("D"):
        print(f"⚠️ 경고: 입력하신 '{channel_id}'가 올바른 슬랙 채널 ID(C...) 형식이 아닌 것 같습니다.")
        print("슬랙 채널 우클릭 -> 채널 세부정보 보기 -> 맨 아래에서 채널 ID를 확인할 수 있습니다.")

    print(f"🚀 Sending mock reservation data to Slack channel: {channel_id}")
    
    # Mock data
    date = "2026-05-20"
    zone = "서울 숲 캠핑장 - A구역 (데크)"
    price = "35,000원"
    
    options = {
        "✅ 승인 및 예약 진행": "approve_reservation_001",
        "❌ 취소": "cancel_reservation_001"
    }
    
    msg_text = (
        f"🙋‍♂️ *ADK 예약 비서가 자리를 찾았습니다!*\n\n"
        f"기념일 근처에 아주 명당 자리가 나왔네요.\n"
        f"• *장소*: {zone}\n"
        f"• *일시*: {date}\n"
        f"• *금액*: {price}\n\n"
        f"지금 바로 예약을 선점할까요?"
    )
    
    success = await notifier.send_action_request(channel_id, msg_text, options)
    
    if success:
        print("✅ Message sent successfully! Check your Slack.")
    else:
        print("❌ Failed to send message. Check your SLACK_BOT_TOKEN and Channel ID.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/tests/test_slack.py <CHANNEL_ID>")
        sys.exit(1)
        
    target_channel = sys.argv[1]
    asyncio.run(test_slack_notification(target_channel))
