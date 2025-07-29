from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from typing import Optional
import os

router = APIRouter()
config = Config(environ=os.environ)

oauth = OAuth(config)
oauth.register(
    name="azure",
    client_id=os.getenv("AZURE_CLIENT_ID"),
    client_secret=os.getenv("AZURE_CLIENT_SECRET"),
    server_metadata_url=f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID')}/v2.0/.well-known/openid-configuration",
    api_base_url="https://graph.microsoft.com/v1.0/",
    client_kwargs={
        "scope": "openid profile email User.Read",
        "code_challenge_method": None
    }
)
def require_login(request: Request) -> dict:
    user: Optional[dict] = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não autenticado.")
    return user

@router.get("/login")
async def login(request: Request):
    redirect_uri = os.getenv("AZURE_REDIRECT_URI")
    return await oauth.azure.authorize_redirect(request, redirect_uri)

@router.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.azure.authorize_access_token(request)

    # Aqui já vem como dict, não precisa await .json()
    user = await oauth.azure.get("me", token=token)
    email = user.get("mail") or user.get("userPrincipalName")
    name = user.get("displayName") or email

    allowed_emails = os.getenv("AZURE_ALLOWED_EMAILS", "").split(",")
    email_ok = email.lower() in [e.strip().lower() for e in allowed_emails]

    if not email_ok:
        raise HTTPException(status_code=403, detail="Acesso não autorizado.")

    request.session["user"] = {
        "email": email,
        "name": name,
    }

    return RedirectResponse(url="/painel")

@router.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/login")
