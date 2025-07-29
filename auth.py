resp = await oauth.azure.get("https://graph.microsoft.com/v1.0/me", token=token)
user = await resp.json()
email = user.get("mail") or user.get("userPrincipalName")from fastapi import APIRouter, Request, HTTPException
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
    authorize_url=f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID')}/oauth2/v2.0/authorize",
    access_token_url=f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID')}/oauth2/v2.0/token",
    client_kwargs={"scope": "User.Read openid email profile"},
    server_metadata_url=f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID')}/v2.0/.well-known/openid-configuration"
)

# 🔐 Verifica sessão ativa
def require_login(request: Request) -> dict:
    user: Optional[dict] = request.session.get("user")
    if not user:
        # Redireciona automaticamente pro login se não autenticado
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user

# 🔁 Login → redireciona pro Azure
@router.get("/login")
async def login(request: Request):
    redirect_uri = os.getenv("AZURE_REDIRECT_URI")
    return await oauth.azure.authorize_redirect(request, redirect_uri)

# 🔁 Callback do Azure após login
@router.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.azure.authorize_access_token(request)
    resp = await oauth.azure.get("https://graph.microsoft.com/v1.0/me", token=token)
    user = await resp.json()

    email = user.get("mail") or user.get("userPrincipalName")
    name = user.get("displayName", email)

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
