import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

@app.get("/", response_class=HTMLResponse)
async def form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/thread", response_class=HTMLResponse)
async def show_thread(request: Request, canal_id: str = Form(...), thread_ts: str = Form(...)):
    try:
        resp = slack_client.conversations_replies(channel=canal_id, ts=thread_ts, limit=200)
        messages = [
            {
                "user": m.get("user", "desconhecido"),
                "text": m.get("text", ""),
                "ts": m.get("ts")
            }
            for m in resp.get("messages", [])
        ]
    except SlackApiError as e:
        return templates.TemplateResponse("thread.html", {
            "request": request, "messages": [], "error": str(e)
        })

    return templates.TemplateResponse("thread.html", {
        "request": request, "messages": messages, "canal": canal_id, "thread": thread_ts
    })
