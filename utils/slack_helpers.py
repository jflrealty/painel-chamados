from functools import lru_cache
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=SLACK_BOT_TOKEN)

@lru_cache(maxsize=1024)
def get_real_name(user_id: str) -> str:
    """Busca o nome real de um usuário do Slack com cache local."""
    if not user_id:
        return "–"
    try:
        info = client.users_info(user=user_id)
        return info["user"].get("real_name", user_id)
    except SlackApiError:
        return user_id
