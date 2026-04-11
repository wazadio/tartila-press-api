from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import require_admin
from app.database import get_db
from app.schemas import BookCreate, BookOut, BookUpdate

router = APIRouter(prefix="/books", tags=["books"])

_BOOK_WITH_AUTHOR = """
    SELECT b.*, a.name AS author, bd.name AS bidang_name
    FROM books b
    LEFT JOIN authors a ON a.id = b.author_id
    LEFT JOIN bidang bd ON bd.id = b.bidang_id
"""


def _row_to_book(row) -> dict:
    d = dict(row)
    d["featured"] = bool(d.get("featured", 0))
    d["is_template"] = bool(d.get("is_template", 0))
    return d


@router.get("", response_model=list[BookOut])
def list_books(
    search: Optional[str] = Query(None),
    genre: Optional[str] = Query(None),
    featured: Optional[bool] = Query(None),
    is_template: Optional[bool] = Query(None),
    bidang_id: Optional[int] = Query(None),
    db = Depends(get_db),
):
    query = _BOOK_WITH_AUTHOR + " WHERE 1=1"
    params: list = []

    if search:
        query += " AND (LOWER(b.title) LIKE %s OR LOWER(a.name) LIKE %s)"
        like = f"%{search.lower()}%"
        params += [like, like]

    if genre:
        query += " AND b.genre = %s"
        params.append(genre)

    if featured is not None:
        query += " AND b.featured = %s"
        params.append(featured)

    if is_template is not None:
        query += " AND b.is_template = %s"
        params.append(is_template)

    if bidang_id is not None:
        query += " AND b.bidang_id = %s"
        params.append(bidang_id)

    query += " ORDER BY b.id"
    rows = db.execute(query, params).fetchall()
    return [_row_to_book(r) for r in rows]


@router.get("/genres")
def list_genres(db = Depends(get_db)):
    rows = db.execute("SELECT DISTINCT genre FROM books ORDER BY genre").fetchall()
    return [r["genre"] for r in rows]


@router.get("/{book_id}", response_model=BookOut)
def get_book(book_id: int, db = Depends(get_db)):
    row = db.execute(_BOOK_WITH_AUTHOR + " WHERE b.id = %s", (book_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")
    return _row_to_book(row)


@router.post("", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def create_book(
    body: BookCreate,
    db = Depends(get_db),
    _: dict = Depends(require_admin),
):
    author = db.execute("SELECT id FROM authors WHERE id = %s", (body.author_id,)).fetchone()
    if not author:
        raise HTTPException(status_code=400, detail="Author not found")

    cur = db.execute(
        """INSERT INTO books
           (title, author_id, cover, genre, published_year, pages, isbn, description, synopsis, price, rating, featured, is_template, bidang_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (
            body.title, body.author_id, body.cover, body.genre,
            body.published_year, body.pages, body.isbn, body.description,
            body.synopsis, body.price, body.rating, body.featured, body.is_template, body.bidang_id,
        ),
    )
    new_id = cur.fetchone()["id"]
    db.commit()

    # Update author's books_published count
    db.execute(
        "UPDATE authors SET books_published = (SELECT COUNT(*) FROM books WHERE author_id = %s) WHERE id = %s",
        (body.author_id, body.author_id),
    )
    db.commit()

    row = db.execute(_BOOK_WITH_AUTHOR + " WHERE b.id = %s", (new_id,)).fetchone()
    return _row_to_book(row)


@router.patch("/{book_id}", response_model=BookOut)
def update_book(
    book_id: int,
    body: BookUpdate,
    db = Depends(get_db),
    _: dict = Depends(require_admin),
):
    row = db.execute("SELECT id FROM books WHERE id = %s", (book_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        row = db.execute(_BOOK_WITH_AUTHOR + " WHERE b.id = %s", (book_id,)).fetchone()
        return _row_to_book(row)

    if "featured" in updates:
        updates["featured"] = bool(updates["featured"])
    if "is_template" in updates:
        updates["is_template"] = bool(updates["is_template"])

    updates["updated_at"] = "CURRENT_TIMESTAMP"
    fields = ", ".join(
        f"{k} = CURRENT_TIMESTAMP" if v == "CURRENT_TIMESTAMP" else f"{k} = %s"
        for k, v in updates.items()
    )
    values = [v for v in updates.values() if v != "CURRENT_TIMESTAMP"]

    db.execute(f"UPDATE books SET {fields} WHERE id = %s", (*values, book_id))
    db.commit()

    row = db.execute(_BOOK_WITH_AUTHOR + " WHERE b.id = %s", (book_id,)).fetchone()
    return _row_to_book(row)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    book_id: int,
    db = Depends(get_db),
    _: dict = Depends(require_admin),
):
    row = db.execute("SELECT author_id FROM books WHERE id = %s", (book_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Book not found")

    author_id = row["author_id"]
    db.execute("DELETE FROM books WHERE id = %s", (book_id,))
    db.commit()

    # Update author's books_published count
    db.execute(
        "UPDATE authors SET books_published = (SELECT COUNT(*) FROM books WHERE author_id = %s) WHERE id = %s",
        (author_id, author_id),
    )
    db.commit()
