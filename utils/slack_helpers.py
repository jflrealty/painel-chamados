import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

def get_real_name(user_id: str) -> str:
    if not user_id:
        return "(sem responsável)"

    if user_id.startswith("S"):  # Provável user group
        try:
            resp = slack_client.usergroups_list()
            groups = resp.get("usergroups", [])
            for g in groups:
                if g.get("id") == user_id:
                    return g.get("name") or user_id
        except SlackApiError:
            return user_id
    else:  # Usuário normal
        try:
            user_info = slack_client.users_info(user=user_id)
            return user_info["user"]["real_name"]
        except SlackApiError:
            return user_id
