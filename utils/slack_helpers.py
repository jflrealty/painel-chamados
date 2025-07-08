import os, re
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# ────── Nomes reais ──────
def get_real_name(user_id: str) -> str:
    if not user_id:
        return "desconhecido"

    # Grupos (começam com “S”)
    if user_id.startswith("S"):
        try:
            for g in slack_client.usergroups_list().get("usergroups", []):
                if g["id"] == user_id:
                    return g.get("name", user_id)
        except SlackApiError:
            pass
        return user_id

    # Usuário comum
    try:
        ui = slack_client.users_info(user=user_id).get("user", {})
        return (
            ui.get("real_name")
            or ui.get("profile", {}).get("real_name_normalized")
            or ui.get("name")
            or user_id
        )
    except SlackApiError:
        return user_id

# ────── Emojis → Unicode ──────
EMOJI_MAP = {
    ":white_check_mark:": "✅",
    ":heavy_check_mark:": "✔️",
    ":x:": "❌",
    ":warning:": "⚠️",
    ":information_source:": "ℹ️",
    ":rocket:": "🚀",
    ":boom:": "💥",
    ":arrows_counterclockwise:": "🔄",
    ":recycle:": "♻️",
    # …adicione mais se quiser
}

GRUPO_MAP = {
    "S08STJCNMHR": "Equipe Reservas",
    # acrescente outros grupos aqui
}

# ────── Texto Slack bonito ──────
def formatar_texto_slack(texto: str) -> str:
    if not texto:
        return ""

    # Substitui :emoji:
    for e, uni in EMOJI_MAP.items():
        texto = texto.replace(e, uni)

    # Menções <@U123>
    texto = re.sub(
        r"<@([A-Z0-9]+)>",
        lambda m: get_real_name(m.group(1)),
        texto,
    )

    # Subteam <!subteam^SID>
    texto = re.sub(
        r"<!subteam\^([A-Z0-9]+)>",
        lambda m: GRUPO_MAP.get(m.group(1), f"[Grupo {m.group(1)}]"),
        texto,
    )

    return texto
