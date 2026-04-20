import os
import aiohttp
import logging

logger = logging.getLogger(__name__)

class SlackNotifier:
    def __init__(self):
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.base_url = "https://slack.com/api/chat.postMessage"

    async def send_message(self, channel_id: str, text: str):
        if not self.bot_token or not channel_id:
            logger.warning("Slack credentials not set. Message not sent: %s", text)
            return False
            
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "channel": channel_id,
            "text": text
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, headers=headers, json=payload) as response:
                    data = await response.json()
                    if not data.get("ok"):
                        logger.error(f"Slack API error: {data.get('error')}")
                        return False
                    return True
            except Exception as e:
                logger.error(f"Error sending Slack message: {e}")
                return False

    async def send_action_request(self, channel_id: str, text: str, options: dict) -> bool:
        """
        Send a message with Block Kit buttons for user action (e.g. Yes/No).
        This connects with HITL (Human In The Loop) in LangGraph/ADK.
        """
        if not self.bot_token or not channel_id:
            logger.warning("Slack config missing. Interactive message not sent.")
            return False
            
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }
        
        # Build Block kit actions
        elements = []
        for text_label, action_id in options.items():
            elements.append({
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": text_label
                },
                "value": action_id,
                "action_id": action_id
            })
            
        payload = {
            "channel": channel_id,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": text
                    }
                },
                {
                    "type": "actions",
                    "elements": elements
                }
            ]
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, headers=headers, json=payload) as response:
                    data = await response.json()
                    return data.get("ok", False)
            except Exception as e:
                logger.error(f"Error sending Slack interactive message: {e}")
                return False
