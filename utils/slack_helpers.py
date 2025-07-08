import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

def get_real_name(user_id: str) -> str:
    if not user_id:
        return "desconhecido"

    if user_id.startswith("S"):  # Provável user group
        try:
            resp = slack_client.usergroups_list()
            for g in resp.get("usergroups", []):
                if g.get("id") == user_id:
                    return g.get("name", user_id)
        except SlackApiError:
            return user_id

    try:
        user_info = slack_client.users_info(user=user_id)
        user = user_info.get("user", {})
        return (
            user.get("real_name") or
            user.get("profile", {}).get("real_name_normalized") or
            user.get("name") or
            user_id
        )
    except SlackApiError:
        return user_id
