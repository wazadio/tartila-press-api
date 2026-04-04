import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import require_admin
from app.database import get_db
from app.schemas import BookCreate, BookOut, BookUpdate

router = APIRouter(prefix="/books", tags=["books"])

_BOOK_WITH_AUTHOR = """
    SELECT b.*, a.name AS author
    FROM books b
    LEFT JOIN authors a ON a.id = b.author_id
"""


def _row_to_book(row) -> dict:
    d = dict(row)
    d["featured"] = bool(d.get("featured", 0))
    return d


@router.get("", response_model=list[BookOut])
def list_books(
    search: Optional[str] = Query(None),
    genre: Optional[str] = Query(None),
    featured: Optional[bool] = Query(None),
    db: sqlite3.Connection = Depends(get_db),
):
    query = _BOOK_WITH_AUTHOR + " WHERE 1=1"
    params: list = []

    if search:
        query += " AND (LOWER(b.title) LIKE ? OR LOWER(a.name) LIKE ?)"
        like = f"%{search.lower()}%"
        params += [like, like]

    if genre:
        query += " AND b.genre = ?"
        params.append(genre)

    if featured is not None:
        query += " AND b.featured = ?"
        params.append(1 if featured else 0)

    query += " ORDER BY b.id"
    rows = db.execute(query, params).fetchall()
    return [_row_to_book(r) for r in rows]


@router.get("/genres")
def list_genres(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT DISTINCT genre FROM books ORDER BY genre").fetchall()
    return [r["genre"] for r in rows]


@router.get("/{book_id}", response_model=BookOut)
def get_book(book_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute(_BOOK_WITH_AUTHOR + " WHERE b.id = ?", (book_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")
    return _row_to_book(row)


@router.post("", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def create_book(
    body: BookCreate,
    db: sqlite3.Connection = Depends(get_db),
    _: dict = Depends(require_admin),
):
    author = db.execute("SELECT id FROM authors WHERE id = ?", (body.author_id,)).fetchone()
    if not author:
        raise HTTPException(status_code=400, detail="Author not found")

    cur = db.execute(
        """INSERT INTO books
           (title, author_id, cover, genre, published_year, pages, isbn, description, price, rating, featured)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            body.title, body.author_id, body.cover, body.genre,
            body.published_year, body.pages, body.isbn, body.description,
            body.price, body.rating, 1 if body.featured else 0,
        ),
    )
    db.commit()

    # Update author's books_published count
    db.execute(
        "UPDATE authors SET books_published = (SELECT COUNT(*) FROM books WHERE author_id = ?) WHERE id = ?",
        (body.author_id, body.author_id),
    )
    db.commit()

    row = db.execute(_BOOK_WITH_AUTHOR + " WHERE b.id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_book(row)


@router.patch("/{book_id}", response_model=BookOut)
def update_book(
    book_id: int,
    body: BookUpdate,
    db: sqlite3.Connection = Depends(get_db),
    _: dict = Depends(require_admin),
):
    row = db.execute("SELECT id FROM books WHERE id = ?", (book_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        row = db.execute(_BOOK_WITH_AUTHOR + " WHERE b.id = ?", (book_id,)).fetchone()
        return _row_to_book(row)

    if "featured" in updates:
        updates["featured"] = 1 if updates["featured"] else 0

    updates["updated_at"] = "CURRENT_TIMESTAMP"
    fields = ", ".join(
        f"{k} = CURRENT_TIMESTAMP" if v == "CURRENT_TIMESTAMP" else f"{k} = ?"
        for k, v in updates.items()
    )
    values = [v for v in updates.values() if v != "CURRENT_TIMESTAMP"]

    db.execute(f"UPDATE books SET {fields} WHERE id = ?", (*values, book_id))
    db.commit()

    row = db.execute(_BOOK_WITH_AUTHOR + " WHERE b.id = ?", (book_id,)).fetchone()
    return _row_to_book(row)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    book_id: int,
    db: sqlite3.Connection = Depends(get_db),
    _: dict = Depends(require_admin),
):
    row = db.execute("SELECT author_id FROM books WHERE id = ?", (book_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")

    author_id = row["author_id"]
    db.execute("DELETE FROM books WHERE id = ?", (book_id,))
    db.commit()

    # Update author's books_published count
    db.execute(
        "UPDATE authors SET books_published = (SELECT COUNT(*) FROM books WHERE author_id = ?) WHERE id = ?",
        (author_id, author_id),
    )
    db.commit()
