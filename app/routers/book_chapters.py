from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_admin
from app.database import get_db
from app.schemas import BookChapterCreate, BookChapterOut

router = APIRouter(prefix="/books/{book_id}/chapters", tags=["book-chapters"])


@router.get("", response_model=list[BookChapterOut])
def list_book_chapters(book_id: int, db=Depends(get_db)):
    book = db.execute("SELECT id FROM books WHERE id = %s", (book_id,)).fetchone()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    rows = db.execute(
        "SELECT * FROM book_chapters WHERE book_id = %s ORDER BY number",
        (book_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.put("", response_model=list[BookChapterOut], status_code=status.HTTP_200_OK)
def replace_book_chapters(
    book_id: int,
    body: list[BookChapterCreate],
    db=Depends(get_db),
    _=Depends(require_admin),
):
    """Replace all sellable chapters for a book in one call."""
    book = db.execute("SELECT id, stock FROM books WHERE id = %s", (book_id,)).fetchone()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    book_stock = book["stock"]
    for ch in body:
        if ch.stock is not None and book_stock is not None and ch.stock > book_stock:
            raise HTTPException(
                status_code=400,
                detail=f"Chapter '{ch.title}' stock ({ch.stock}) cannot exceed book stock ({book_stock}).",
            )

    db.execute("DELETE FROM book_chapters WHERE book_id = %s", (book_id,))
    for ch in body:
        db.execute(
            "INSERT INTO book_chapters (book_id, number, title, price, stock) VALUES (%s, %s, %s, %s, %s)",
            (book_id, ch.number, ch.title, ch.price, ch.stock),
        )
    db.commit()

    rows = db.execute(
        "SELECT * FROM book_chapters WHERE book_id = %s ORDER BY number",
        (book_id,),
    ).fetchall()
    return [dict(r) for r in rows]
