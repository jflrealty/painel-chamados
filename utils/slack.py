import os
from slack_sdk import WebClient
import streamlit as st      # ← adicione

# tenta st.secrets primeiro; se não existir usa env var
token = st.secrets.get("SLACK_BOT_TOKEN", os.getenv("SLACK_BOT_TOKEN", ""))

client = WebClient(token=token)
_cache_usuarios = {}

def get_nome_real(user_id):
    if not user_id or not isinstance(user_id, str):
        return "–"

    if user_id == "S08STJCNMHR":
        return "Reservas"

    if not user_id.startswith("U"):
        return "–"

    if user_id in _cache_usuarios:
        return _cache_usuarios[user_id]

    try:
        user = client.users_info(user=user_id)
        nome = user["user"]["real_name"]
        _cache_usuarios[user_id] = nome
        return nome
    except Exception:
        return "–"
