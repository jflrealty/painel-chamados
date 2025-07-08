import os
import re
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

EMOJI_MAP = {
    ":white_check_mark:": "✅",
    ":heavy_check_mark:": "✔️",
    ":x:": "❌",
    ":warning:": "⚠️",
    ":information_source:": "ℹ️",
    ":rocket:": "🚀",
    ":boom:": "💥",
    ":arrows_counterclockwise:": "🔄",
    ":clipboard:": "📋",
    ":hourglass_flowing_sand:": "⏳",
    ":hourglass:": "⌛",
    ":memo:": "📝",
    ":eyes:": "👀",
    ":wastebasket:": "🗑️",
    ":lock:": "🔒",
    ":unlock:": "🔓",
    ":key:": "🔑",
    ":calendar:": "📅",
    ":phone:": "📞",
    ":email:": "✉️",
    ":pushpin:": "📌",
    ":mag:": "🔍",
    ":question:": "❓",
    ":star:": "⭐",
    ":star2:": "🌟",
    ":bulb:": "💡",
    ":gear:": "⚙️",
    ":house:": "🏠",
    ":computer:": "💻",
    ":chart_with_upwards_trend:": "📈",
    ":bar_chart:": "📊"
}

GRUPO_MAP = {
    "S08STJCNMHR": "Equipe Reservas",
    # Adicione outros grupos aqui
}

def formatar_texto_slack(texto: str) -> str:
    if not texto:
        return ""

    # Emojis tipo :rocket:
    for emoji, simbolo in EMOJI_MAP.items():
        texto = texto.replace(emoji, simbolo)

    # Menções tipo <@U123>
    texto = re.sub(
        r"<@([A-Z0-9]+)>",
        lambda m: get_real_name(m.group(1)) or f"@{m.group(1)}",
        texto
    )

    # Grupos tipo <!subteam^S08STJCNMHR>
    texto = re.sub(
        r"<!subteam\^([A-Z0-9]+)>",
        lambda m: GRUPO_MAP.get(m.group(1), f"[Grupo {m.group(1)}]"),
        texto
    )

    return texto
