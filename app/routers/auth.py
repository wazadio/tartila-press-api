import asyncio
import os
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.email import send_verification_email, send_welcome_email
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, WriterRegisterRequest
import json

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

router = APIRouter(prefix="/auth", tags=["auth"])


def _make_verify_link(token: str) -> str:
    return f"{FRONTEND_URL}/auth/verify?token={token}"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, background_tasks: BackgroundTasks, db = Depends(get_db)):
    existing = db.execute("SELECT id FROM users WHERE email = %s", (body.email,)).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = hash_password(body.password)
    verification_token = secrets.token_urlsafe(32)

    cur = db.execute(
        "INSERT INTO users (name, email, password, role, is_verified, verification_token) VALUES (%s, %s, %s, 'user', FALSE, %s) RETURNING id",
        (body.name, body.email, hashed, verification_token),
    )
    user_id = cur.fetchone()["id"]
    db.commit()
    # Return a token but mark user as unverified — FE will redirect to check-email
    token = create_access_token({"sub": str(user_id), "email": body.email, "name": body.name, "role": "user"})

    verify_link = _make_verify_link(verification_token)
    background_tasks.add_task(_send_verification, body.email, body.name, verify_link)

    return TokenResponse(
        access_token=token,
        user={"id": user_id, "name": body.name, "email": body.email, "role": "user", "is_verified": False},
    )


@router.post("/register/writer", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_writer(body: WriterRegisterRequest, background_tasks: BackgroundTasks, db = Depends(get_db)):
    existing = db.execute("SELECT id FROM users WHERE email = %s", (body.email,)).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = hash_password(body.password)
    verification_token = secrets.token_urlsafe(32)

    cur = db.execute(
        "INSERT INTO users (name, email, password, role, is_verified, verification_token) VALUES (%s, %s, %s, 'writer', FALSE, %s) RETURNING id",
        (body.name, body.email, hashed, verification_token),
    )
    user_id = cur.fetchone()["id"]
    db.commit()

    # Create an authors row linked to this user; writer completes profile from dashboard
    db.execute(
        "INSERT INTO authors (user_id, name, genres) VALUES (%s, %s, %s)",
        (user_id, body.name, json.dumps([])),
    )
    db.commit()

    token = create_access_token({"sub": str(user_id), "email": body.email, "name": body.name, "role": "writer"})
    verify_link = _make_verify_link(verification_token)
    background_tasks.add_task(_send_verification, body.email, body.name, verify_link)

    return TokenResponse(
        access_token=token,
        user={"id": user_id, "name": body.name, "email": body.email, "role": "writer", "is_verified": False},
    )


def _send_verification(email: str, name: str, verify_link: str):
    asyncio.run(send_verification_email(email, name, verify_link))


def _send_welcome(email: str, name: str):
    asyncio.run(send_welcome_email(email, name))


@router.get("/verify")
def verify_email(token: str, db = Depends(get_db)):
    user = db.execute("SELECT * FROM users WHERE verification_token = %s", (token,)).fetchone()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link.")
    if user["is_verified"]:
        raise HTTPException(status_code=400, detail="Email already verified.")

    db.execute(
        "UPDATE users SET is_verified = TRUE, verification_token = NULL WHERE id = %s",
        (user["id"],),
    )
    db.commit()

    # Send welcome email after successful verification
    try:
        asyncio.run(send_welcome_email(user["email"], user["name"]))
    except Exception as e:
        print(f"[auth] welcome email failed: {e}")

    jwt = create_access_token({
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
    })
    return {"access_token": jwt, "user": dict(user)}


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db = Depends(get_db)):
    row = db.execute("SELECT * FROM users WHERE email = %s", (body.email,)).fetchone()
    if not row or not verify_password(body.password, row["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not row["is_verified"]:
        raise HTTPException(status_code=403, detail="Please verify your email before logging in.")

    token = create_access_token(
        {"sub": str(row["id"]), "email": row["email"], "name": row["name"], "role": row["role"]}
    )
    return TokenResponse(
        access_token=token,
        user={"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"], "is_verified": True},
    )


@router.get("/me")
def me(user: dict = Depends(get_current_user), db = Depends(get_db)):
    row = db.execute("SELECT id, name, email, role, is_verified FROM users WHERE id = %s", (user["sub"],)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)
