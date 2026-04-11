import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status

from app.auth import decode_token, get_current_user, require_admin
from app.database import get_db
from app.email import send_payment_invoice_email
from app.schemas import PaymentConfigOut, TransactionCreate, TransactionOut, TransactionUpdate

router = APIRouter(prefix="/transactions", tags=["transactions"])

BANK_ACCOUNT_NUMBER = os.getenv("BANK_ACCOUNT_NUMBER", "")
BANK_ACCOUNT_NAME = os.getenv("BANK_ACCOUNT_NAME", "")
BANK_NAME = os.getenv("BANK_NAME", "")


def _bank_number() -> str:
    return BANK_ACCOUNT_NUMBER.strip()


def _bank_name() -> str:
    return BANK_ACCOUNT_NAME.strip()


def _bank() -> str:
    return BANK_NAME.strip()


def _as_wib(value: Optional[str]) -> Optional[str]:
    if not value:
        return value

    raw = str(value).strip()
    dt: Optional[datetime] = None

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return raw

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(ZoneInfo("Asia/Jakarta")).isoformat(timespec="seconds")


def _to_transaction_out(row) -> dict:
    out = dict(row)
    out["created_at"] = _as_wib(out.get("created_at"))
    out["bank_name"] = _bank()
    out["bank_account_name"] = _bank_name()
    out["bank_account_number"] = _bank_number()
    # fill optional user fields if not present in row
    if "user_role" not in out:
        out["user_role"] = None
    if "user_is_verified" not in out:
        out["user_is_verified"] = None
    # parse chapter_ids JSON string → list
    raw_ids = out.get("chapter_ids", "[]")
    try:
        out["chapter_ids"] = json.loads(raw_ids) if isinstance(raw_ids, str) else (raw_ids or [])
    except (ValueError, TypeError):
        out["chapter_ids"] = []
    out["stock_exhausted"] = bool(out.get("stock_exhausted", False))
    return out


def _send_payment_invoice(
    to: str,
    name: str,
    transaction_id: int,
    package_name: str,
    total_amount: int,
    payment_status: str,
):
    asyncio.run(
        send_payment_invoice_email(
            to=to,
            name=name,
            transaction_id=transaction_id,
            package_name=package_name,
            total_amount=total_amount,
            bank_name=_bank(),
            bank_account_name=_bank_name(),
            bank_account_number=_bank_number(),
            payment_status=payment_status,
        )
    )


@router.get("/config", response_model=PaymentConfigOut)
def payment_config():
    return {
        "bank_name": _bank(),
        "bank_account_name": _bank_name(),
        "bank_account_number": _bank_number(),
    }


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    body: TransactionCreate,
    background_tasks: BackgroundTasks,
    db = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    package_row = db.execute("SELECT * FROM packages WHERE id = %s", (body.package_id,)).fetchone()
    if not package_row:
        raise HTTPException(status_code=404, detail="Package not found")

    package_price = int(package_row["price"] or 0)
    package_discount = int(package_row["discount"] or 0)
    unit_price = round(package_price * (1 - package_discount / 100))

    chapters = int(body.chapters or 1)
    if chapters < 1:
        raise HTTPException(status_code=400, detail="chapters must be at least 1")

    if package_row["type"] == "per_chapter":
        total_amount = unit_price * chapters
    else:
        chapters = 1
        total_amount = unit_price

    user_id = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_token(token)
        if payload and payload.get("sub"):
            try:
                user_id = int(payload["sub"])
            except (TypeError, ValueError):
                user_id = None

    cur = db.execute(
        """
        INSERT INTO transactions (
            user_id, package_id, package_name, package_type, unit_price, chapters, total_amount,
            book_title, genre, customer_name, customer_email, customer_phone, notes, status, delivery_deadline,
            book_id, chapter_ids
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'unpaid', NULL, %s, %s) RETURNING id
        """,
        (
            user_id,
            package_row["id"],
            package_row["name"],
            package_row["type"],
            unit_price,
            chapters,
            total_amount,
            body.book_title.strip(),
            body.genre.strip(),
            body.customer_name.strip(),
            body.customer_email,
            body.customer_phone.strip(),
            body.notes.strip() if body.notes else None,
            body.book_id,
            json.dumps(body.chapter_ids or []),
        ),
    )
    new_id = cur.fetchone()["id"]
    db.commit()

    row = db.execute("SELECT * FROM transactions WHERE id = %s", (new_id,)).fetchone()
    background_tasks.add_task(
        _send_payment_invoice,
        body.customer_email,
        body.customer_name.strip(),
        int(row["id"]),
        str(row["package_name"]),
        int(row["total_amount"]),
        str(row["status"]),
    )
    return _to_transaction_out(row)


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    db = Depends(get_db),
    _: dict = Depends(require_admin),
):
    rows = db.execute(
        """
        SELECT t.*,
               u.role   AS user_role,
               u.is_verified AS user_is_verified
        FROM transactions t
        LEFT JOIN users u ON u.id = t.user_id
        ORDER BY t.id DESC
        """
    ).fetchall()
    return [_to_transaction_out(r) for r in rows]


@router.get("/mine", response_model=list[TransactionOut])
def list_my_transactions(
    db = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    rows = db.execute(
        "SELECT * FROM transactions WHERE user_id = %s ORDER BY id DESC",
        (int(user["sub"]),),
    ).fetchall()
    return [_to_transaction_out(r) for r in rows]


@router.patch("/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: int,
    body: TransactionUpdate,
    db = Depends(get_db),
    _: dict = Depends(require_admin),
):
    row = db.execute("SELECT * FROM transactions WHERE id = %s", (transaction_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return _to_transaction_out(row)

    current_status = row["status"]
    next_status = updates.get("status", current_status)

    # ── Stock check when marking as paid ─────────────────────────────────────
    if next_status == "paid" and current_status != "paid":
        book_id = row.get("book_id")
        try:
            chapter_ids = json.loads(row.get("chapter_ids") or "[]")
        except (ValueError, TypeError):
            chapter_ids = []

        stock_problem = None

        if book_id:
            book_row = db.execute("SELECT title, stock FROM books WHERE id = %s", (book_id,)).fetchone()
            if book_row and book_row["stock"] is not None and book_row["stock"] <= 0:
                stock_problem = f"Stok buku '{book_row['title']}' sudah habis."

        if stock_problem is None and chapter_ids:
            for ch_id in chapter_ids:
                ch_row = db.execute("SELECT title, stock FROM book_chapters WHERE id = %s", (ch_id,)).fetchone()
                if ch_row and ch_row["stock"] is not None and ch_row["stock"] <= 0:
                    stock_problem = f"Stok bab '{ch_row['title']}' sudah habis."
                    break

        if stock_problem:
            # Flag the transaction as stock-exhausted and abort status change
            db.execute(
                "UPDATE transactions SET stock_exhausted = TRUE WHERE id = %s",
                (transaction_id,),
            )
            db.commit()
            raise HTTPException(status_code=409, detail=stock_problem)

        # All stock OK — decrement and clear any previous exhausted flag
        if book_id:
            db.execute(
                "UPDATE books SET stock = stock - 1 WHERE id = %s AND stock IS NOT NULL AND stock > 0",
                (book_id,),
            )
        for ch_id in chapter_ids:
            db.execute(
                "UPDATE book_chapters SET stock = stock - 1 WHERE id = %s AND stock IS NOT NULL AND stock > 0",
                (ch_id,),
            )
        updates["stock_exhausted"] = False
    # ─────────────────────────────────────────────────────────────────────────

    if (
        "delivery_deadline" in updates
        and updates["delivery_deadline"] is not None
        and (current_status != "unpaid" or next_status != "unpaid")
    ):
        raise HTTPException(status_code=400, detail="Delivery deadline can only be set when status is unpaid")

    if "delivery_deadline" in updates:
        deadline = updates["delivery_deadline"]
        updates["delivery_deadline"] = deadline.strip() if deadline else None

    fields = ", ".join(f"{k} = %s" for k in updates)
    db.execute(f"UPDATE transactions SET {fields} WHERE id = %s", (*updates.values(), transaction_id))
    db.commit()

    updated_row = db.execute("SELECT * FROM transactions WHERE id = %s", (transaction_id,)).fetchone()
    return _to_transaction_out(updated_row)
