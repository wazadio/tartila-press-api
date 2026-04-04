import json

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_admin, require_writer
from app.database import get_db
from app.schemas import AuthorCreate, AuthorOut, AuthorUpdate, WriterOut, WriterUpdate

router = APIRouter(prefix="/authors", tags=["authors"])


def _row_to_author(row) -> dict:
    d = dict(row)
    d["genres"] = json.loads(d.get("genres") or "[]")
    d.pop("user_id", None)
    return d


def _row_to_writer(row) -> dict:
    genres = row["genres"]
    if isinstance(genres, str):
        try:
            genres = json.loads(genres)
        except Exception:
            genres = []
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "photo": row["photo"],
        "bio": row["bio"],
        "nationality": row["nationality"],
        "books_published": row["books_published"],
        "genres": genres,
        "website": row["website"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


# ── Writer endpoints (must be before /{author_id}) ────────────────────────────

@router.get("/writers", response_model=list[WriterOut])
def list_writers(db = Depends(get_db), _: dict = Depends(require_admin)):
    rows = db.execute("""
        SELECT a.id, a.user_id, a.name, a.photo, a.bio, a.nationality,
               a.books_published, a.genres, a.website, a.created_at,
               u.email
        FROM authors a
        JOIN users u ON u.id = a.user_id
        WHERE a.user_id IS NOT NULL
        ORDER BY a.created_at DESC
    """).fetchall()
    return [_row_to_writer(r) for r in rows]


@router.get("/me", response_model=WriterOut)
def get_my_profile(db = Depends(get_db), user: dict = Depends(require_writer)):
    row = db.execute("""
        SELECT a.id, a.user_id, a.name, a.photo, a.bio, a.nationality,
               a.books_published, a.genres, a.website, a.created_at,
               u.email
        FROM authors a
        JOIN users u ON u.id = a.user_id
        WHERE a.user_id = %s
    """, (user["sub"],)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Writer profile not found")
    return _row_to_writer(row)


@router.patch("/me", response_model=WriterOut)
def update_my_profile(body: WriterUpdate, db = Depends(get_db), user: dict = Depends(require_writer)):
    row = db.execute("SELECT id FROM authors WHERE user_id = %s", (user["sub"],)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Writer profile not found")

    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.photo is not None:
        updates["photo"] = body.photo
    if body.bio is not None:
        updates["bio"] = body.bio
    if body.nationality is not None:
        updates["nationality"] = body.nationality
    if body.genres is not None:
        updates["genres"] = json.dumps(body.genres)
    if body.website is not None:
        updates["website"] = body.website

    if updates:
        sets = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [row["id"]]
        db.execute(f"UPDATE authors SET {sets} WHERE id = %s", values)
        db.commit()

    updated = db.execute("""
        SELECT a.id, a.user_id, a.name, a.photo, a.bio, a.nationality,
               a.books_published, a.genres, a.website, a.created_at,
               u.email
        FROM authors a JOIN users u ON u.id = a.user_id WHERE a.user_id = %s
    """, (user["sub"],)).fetchone()
    return _row_to_writer(updated)


# ── Author CRUD ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[AuthorOut])
def list_authors(db = Depends(get_db)):
    rows = db.execute("SELECT * FROM authors ORDER BY id").fetchall()
    return [_row_to_author(r) for r in rows]


@router.get("/{author_id}", response_model=AuthorOut)
def get_author(author_id: int, db = Depends(get_db)):
    row = db.execute("SELECT * FROM authors WHERE id = %s", (author_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Author not found")
    return _row_to_author(row)


@router.post("", response_model=AuthorOut, status_code=status.HTTP_201_CREATED)
def create_author(
    body: AuthorCreate,
    db = Depends(get_db),
    _: dict = Depends(require_admin),
):
    cur = db.execute(
        """INSERT INTO authors (name, photo, bio, nationality, books_published, genres, website)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (
            body.name, body.photo, body.bio, body.nationality,
            body.books_published, json.dumps(body.genres or []), body.website,
        ),
    )
    new_id = cur.fetchone()["id"]
    db.commit()
    row = db.execute("SELECT * FROM authors WHERE id = %s", (new_id,)).fetchone()
    return _row_to_author(row)


@router.patch("/{author_id}", response_model=AuthorOut)
def update_author(
    author_id: int,
    body: AuthorUpdate,
    db = Depends(get_db),
    _: dict = Depends(require_admin),
):
    row = db.execute("SELECT * FROM authors WHERE id = %s", (author_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Author not found")

    current = _row_to_author(row)
    updates = body.model_dump(exclude_unset=True)
    if "genres" in updates:
        updates["genres"] = json.dumps(updates["genres"])

    if not updates:
        return current

    fields = ", ".join(f"{k} = %s" for k in updates)
    db.execute(f"UPDATE authors SET {fields} WHERE id = %s", (*updates.values(), author_id))
    db.commit()
    row = db.execute("SELECT * FROM authors WHERE id = %s", (author_id,)).fetchone()
    return _row_to_author(row)


@router.delete("/{author_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_author(
    author_id: int,
    db = Depends(get_db),
    _: dict = Depends(require_admin),
):
    row = db.execute("SELECT id, user_id FROM authors WHERE id = %s", (author_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Author not found")
    # If linked to a user account (writer), delete the user too (cascades to authors row)
    if row["user_id"]:
        db.execute("DELETE FROM users WHERE id = %s", (row["user_id"],))
    else:
        db.execute("DELETE FROM authors WHERE id = %s", (author_id,))
    db.commit()
