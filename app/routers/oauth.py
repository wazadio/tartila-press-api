import os
import secrets

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.auth import create_access_token, hash_password
from app.database import get_db
from app.email import send_welcome_email

load_dotenv(dotenv_path="/app/.env", override=True)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

router = APIRouter(prefix="/auth", tags=["oauth"])


def _google_redirect(state: str = "user") -> RedirectResponse:
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("REDIRECT_URI", "http://localhost:3001/api/auth/google/callback")
    if not google_client_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google OAuth not configured.")
    params = (
        f"client_id={google_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
        f"&prompt=select_account"
        f"&state={state}"
    )
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{params}")


@router.get("/google")
def google_login():
    return _google_redirect(state="user")


@router.get("/google/writer")
def google_writer_login():
    return _google_redirect(state="writer")


@router.get("/google/callback")
async def google_callback(code: str = None, error: str = None, state: str = "user", background_tasks: BackgroundTasks = None, db=Depends(get_db)):
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("REDIRECT_URI", "http://localhost:3001/api/auth/google/callback")

    # Determine intended role from state
    intended_role = "writer" if state == "writer" else "user"
    error_redirect = f"{frontend_url}/writer/register" if intended_role == "writer" else f"{frontend_url}/login"

    if error or not code:
        return RedirectResponse(f"{error_redirect}?error=google_denied")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_res = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code,
                "client_id": google_client_id,
                "client_secret": google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            print(f"[oauth] token status={token_res.status_code} body={token_res.text[:300]}")
            if token_res.status_code != 200:
                return RedirectResponse(f"{error_redirect}?error=google_token_failed")

            tokens = token_res.json()
            access_token = tokens.get("access_token")
            if not access_token:
                return RedirectResponse(f"{error_redirect}?error=google_token_failed")

            userinfo_res = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            print(f"[oauth] userinfo status={userinfo_res.status_code}")
            if userinfo_res.status_code != 200:
                return RedirectResponse(f"{error_redirect}?error=google_userinfo_failed")

            userinfo = userinfo_res.json()
    except httpx.ConnectTimeout:
        print("[oauth] ConnectTimeout reaching Google")
        return RedirectResponse(f"{error_redirect}?error=google_timeout")
    except Exception as e:
        print(f"[oauth] Exception {type(e).__name__}: {e}")
        return RedirectResponse(f"{error_redirect}?error=google_network_error")

    email = userinfo.get("email")
    name = userinfo.get("name") or email
    if not email:
        return RedirectResponse(f"{error_redirect}?error=google_no_email")

    # Find or create user — always set is_verified=TRUE for OAuth users
    user = db.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
    is_new = not user
    if is_new:
        # New user: assign intended role, mark verified immediately
        db.execute(
            "INSERT INTO users (name, email, password, role, is_verified, verification_token) "
            "VALUES (%s, %s, %s, %s, TRUE, NULL)",
            (name, email, hash_password(secrets.token_hex(32)), intended_role),
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
        background_tasks.add_task(send_welcome_email, email, name)
    else:
        # Existing user: mark verified (email confirmed via Google), preserve role
        db.execute(
            "UPDATE users SET is_verified = TRUE, verification_token = NULL WHERE id = %s",
            (user["id"],),
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()

    jwt = create_access_token({
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
    })

    return RedirectResponse(f"{frontend_url}/auth/callback?token={jwt}")
