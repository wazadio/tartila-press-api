import asyncio
import os
import secrets

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.auth import create_access_token, hash_password
from app.database import get_db
from app.email import send_welcome_email

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
REDIRECT_URI = "https://color-max-addition-fibre.trycloudflare.com/api/auth/google/callback"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

router = APIRouter(prefix="/auth", tags=["oauth"])


@router.get("/google")
def google_login():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google OAuth not configured.")
    params = (
        f"client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
        f"&prompt=select_account"
    )
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{params}")


@router.get("/google/callback")
async def google_callback(code: str = None, error: str = None, db=Depends(get_db)):
    if error or not code:
        return RedirectResponse(f"{FRONTEND_URL}/login?error=google_denied")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Exchange code for tokens
            token_res = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            })
            print(f"[oauth] token status={token_res.status_code} body={token_res.text[:300]}")
            if token_res.status_code != 200:
                return RedirectResponse(f"{FRONTEND_URL}/login?error=google_token_failed")

            tokens = token_res.json()
            access_token = tokens.get("access_token")
            if not access_token:
                return RedirectResponse(f"{FRONTEND_URL}/login?error=google_token_failed")

            # Fetch user info
            userinfo_res = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            print(f"[oauth] userinfo status={userinfo_res.status_code}")
            if userinfo_res.status_code != 200:
                return RedirectResponse(f"{FRONTEND_URL}/login?error=google_userinfo_failed")

            userinfo = userinfo_res.json()
    except httpx.ConnectTimeout:
        print("[oauth] ConnectTimeout reaching Google")
        return RedirectResponse(f"{FRONTEND_URL}/login?error=google_timeout")
    except Exception as e:
        print(f"[oauth] Exception {type(e).__name__}: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/login?error=google_network_error")

    email = userinfo.get("email")
    name = userinfo.get("name") or email
    if not email:
        return RedirectResponse(f"{FRONTEND_URL}/login?error=google_no_email")

    # Find or create user
    user = db.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
    is_new = not user
    if is_new:
        db.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, 'user')",
            (name, email, hash_password(secrets.token_hex(32))),
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
        try:
            asyncio.run(send_welcome_email(email, name))
        except Exception as e:
            print(f"[oauth] welcome email failed: {e}")

    jwt = create_access_token({
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
    })

    return RedirectResponse(f"{FRONTEND_URL}/auth/callback?token={jwt}")
