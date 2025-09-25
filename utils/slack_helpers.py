import os, re
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Tokens de ambos os bots
SLACK_BOT_TOKEN_COMERCIAL = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_BOT_TOKEN_FINANCEIRO = os.getenv("SLACK_BOT_TOKEN_FINANCEIRO", "")

# Clientes separados
slack_client_comercial = WebClient(token=SLACK_BOT_TOKEN_COMERCIAL)
slack_client_financeiro = WebClient(token=SLACK_BOT_TOKEN_FINANCEIRO)

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

# ────── Retorna o cliente Slack correto baseado no canal ──────
def get_slack_client(canal_id: str = None) -> WebClient:
    if canal_id == "C08KMCDNEFR":  # ID do canal financeiro
        return slack_client_financeiro
    return slack_client_comercial

# ────── Buscar nome real do usuário ──────
def get_real_name(user_id: str, canal_id: str = None) -> str:
    if not user_id or not isinstance(user_id, str):
        return "<não capturado>"

    client = get_slack_client(canal_id)

    # Grupos (começam com “S”)
    if user_id.startswith("S"):
        try:
            grupos = client.usergroups_list().get("usergroups", [])
            for g in grupos:
                if g["id"] == user_id:
                    return g.get("name", GRUPO_MAP.get(user_id, f"<grupo:{user_id}>"))
        except SlackApiError:
            pass
        return GRUPO_MAP.get(user_id, f"<grupo:{user_id}>")

    # Usuário comum
    try:
        user_info = client.users_info(user=user_id).get("user", {})
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
def formatar_texto_slack(texto: str, canal_id: str = None) -> str:
    if not texto:
        return ""

    # Emojis :emoji: → unicode
    for e, uni in EMOJI_MAP.items():
        texto = texto.replace(e, uni)

    # Substitui usuários <@U123>
    texto = re.sub(
        r"<@([A-Z0-9]+)>",
        lambda m: get_real_name(m.group(1), canal_id),
        texto,
    )

    # Substitui grupos <!subteam^SID>
    texto = re.sub(
        r"<!subteam\^([A-Z0-9]+)>",
        lambda m: GRUPO_MAP.get(m.group(1), f"<grupo:{m.group(1)}>"),
        texto,
    )

    return texto
