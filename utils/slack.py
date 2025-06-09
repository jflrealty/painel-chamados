{\rtf1\ansi\ansicpg1252\cocoartf2822
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww28600\viewh15380\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 import os\
from slack_sdk import WebClient\
\
client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])\
\
_cache_usuarios = \{\}\
\
def get_nome_real(user_id):\
    if not user_id or not user_id.startswith("U"):\
        return user_id\
    if user_id in _cache_usuarios:\
        return _cache_usuarios[user_id]\
    try:\
        user = client.users_info(user=user_id)\
        nome = user["user"]["real_name"]\
        _cache_usuarios[user_id] = nome\
        return nome\
    except Exception as e:\
        return user_id}