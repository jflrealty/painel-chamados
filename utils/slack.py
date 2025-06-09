import os
from slack_sdk import WebClient

client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])

_cache_usuarios = {}

def get_nome_real(user_id):
    if not user_id or not user_id.startswith("U"):
        return user_id
    if user_id in _cache_usuarios:
        return _cache_usuarios[user_id]
    try:
        user = client.users_info(user=user_id)
        nome = user["user"]["real_name"]
        _cache_usuarios[user_id] = nome
        return nome
    except Exception as e:
        return user_id
