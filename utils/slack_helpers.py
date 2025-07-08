import os, re
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# ────── Grupos nomeados manualmente ──────
GRUPO_MAP = {
    "S08STJCNMHR": "Equipe Reservas",
    # Adicione mais se quiser
}

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
    ":hourglass:": "⏳",
    ":memo:": "📝",
    ":bell:": "🔔",
    ":star:": "⭐️",
    ":smile:": "😄",
    ":thumbsup:": "👍",
    ":fire:": "🔥",
    ":zap:": "⚡",
    ":clap:": "👏",
}

# ────── Buscar nome real do usuário ──────
def get_real_name(user_id: str) -> str:
    if not user_id or not isinstance(user_id, str):
        return "<não capturado>"

    # Grupos (começam com “S”)
    if user_id.startswith("S"):
        try:
            grupos = slack_client.usergroups_list().get("usergroups", [])
            for g in grupos:
                if g["id"] == user_id:
                    return g.get("name", GRUPO_MAP.get(user_id, f"<grupo:{user_id}>"))
        except SlackApiError:
            pass
        return GRUPO_MAP.get(user_id, f"<grupo:{user_id}>")

    # Usuário comum
    try:
        user_info = slack_client.users_info(user=user_id).get("user", {})
        nome = (
            user_info.get("real_name") or
            user_info.get("profile", {}).get("real_name_normalized") or
            user_info.get("name")
        )
        if nome and not nome.startswith("U"):  # Evita ID cru
            return nome
    except SlackApiError:
        pass

    return "<não capturado>"

# ────── Formatar mensagens Slack para exibição ──────
def formatar_texto_slack(texto: str) -> str:
    if not texto:
        return ""

    # Emojis :emoji: → unicode
    for e, uni in EMOJI_MAP.items():
        texto = texto.replace(e, uni)

    # Substitui usuários <@U123>
    texto = re.sub(
        r"<@([A-Z0-9]+)>",
        lambda m: get_real_name(m.group(1)),
        texto,
    )

    # Substitui grupos <!subteam^SID>
    texto = re.sub(
        r"<!subteam\^([A-Z0-9]+)>",
        lambda m: GRUPO_MAP.get(m.group(1), f"<grupo:{m.group(1)}>"),
        texto,
    )

    return texto
