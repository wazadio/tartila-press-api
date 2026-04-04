import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_admin
from app.database import get_db
from app.schemas import GenreCreate, GenreOut

router = APIRouter(prefix="/genres", tags=["genres"])


@router.get("/", response_model=list[GenreOut])
def list_genres(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM genres ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@router.post("/", response_model=GenreOut, status_code=status.HTTP_201_CREATED)
def create_genre(body: GenreCreate, db: sqlite3.Connection = Depends(get_db), _=Depends(require_admin)):
    existing = db.execute("SELECT id FROM genres WHERE LOWER(name) = LOWER(?)", (body.name,)).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail="Genre already exists")
    cur = db.execute("INSERT INTO genres (name, name_id) VALUES (?, ?)", (body.name, body.name_id))
    db.commit()
    row = db.execute("SELECT * FROM genres WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.patch("/{genre_id}", response_model=GenreOut)
def update_genre(genre_id: int, body: GenreCreate, db: sqlite3.Connection = Depends(get_db), _=Depends(require_admin)):
    row = db.execute("SELECT * FROM genres WHERE id = ?", (genre_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Genre not found")
    conflict = db.execute("SELECT id FROM genres WHERE LOWER(name) = LOWER(?) AND id != ?", (body.name, genre_id)).fetchone()
    if conflict:
        raise HTTPException(status_code=400, detail="Genre name already exists")
    db.execute("UPDATE genres SET name = ?, name_id = ? WHERE id = ?", (body.name, body.name_id, genre_id))
    db.commit()
    row = db.execute("SELECT * FROM genres WHERE id = ?", (genre_id,)).fetchone()
    return dict(row)


@router.delete("/{genre_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_genre(genre_id: int, db: sqlite3.Connection = Depends(get_db), _=Depends(require_admin)):
    row = db.execute("SELECT id FROM genres WHERE id = ?", (genre_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Genre not found")
    db.execute("DELETE FROM genres WHERE id = ?", (genre_id,))
    db.commit()
