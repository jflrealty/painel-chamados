from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
import os

router = APIRouter()
config = Config(environ=os.environ)

oauth = OAuth(config)
oauth.register(
    name="azure",
    client_id=os.getenv("AZURE_CLIENT_ID"),
    client_secret=os.getenv("AZURE_CLIENT_SECRET"),
    authorize_url="https://login.microsoftonline.com/{}/oauth2/v2.0/authorize".format(os.getenv("AZURE_TENANT_ID")),
    access_token_url="https://login.microsoftonline.com/{}/oauth2/v2.0/token".format(os.getenv("AZURE_TENANT_ID")),
    client_kwargs={"scope": "User.Read openid email profile"},
)

@router.get("/login")
async def login(request: Request):
    redirect_uri = os.getenv("AZURE_REDIRECT_URI")
    return await oauth.azure.authorize_redirect(request, redirect_uri)

@router.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.azure.authorize_access_token(request)
    user = await oauth.azure.parse_id_token(request, token)
    email = user.get("preferred_username")

    # Limita por e-mail (ou domínio, se quiser depois)
    allowed_emails = os.getenv("AZURE_ALLOWED_EMAILS", "").split(",")
    email_ok = email.lower() in [e.strip().lower() for e in allowed_emails]

    if not email_ok:
        raise HTTPException(status_code=403, detail="Acesso não autorizado.")

    request.session["user"] = {
        "email": email,
        "name": user.get("name"),
    }
    return RedirectResponse(url="/painel")

@router.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/login")
