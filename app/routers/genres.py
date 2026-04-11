from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_admin
from app.database import get_db
from app.schemas import GenreCreate, GenreOut

router = APIRouter(prefix="/genres", tags=["genres"])

_GENRE_WITH_BIDANG = """
    SELECT g.*, b.name AS bidang_name
    FROM genres g
    LEFT JOIN bidang b ON b.id = g.bidang_id
"""


@router.get("", response_model=list[GenreOut])
def list_genres(db = Depends(get_db)):
    rows = db.execute(_GENRE_WITH_BIDANG + " ORDER BY g.name").fetchall()
    return [dict(r) for r in rows]


@router.post("", response_model=GenreOut, status_code=status.HTTP_201_CREATED)
def create_genre(body: GenreCreate, db = Depends(get_db), _=Depends(require_admin)):
    existing = db.execute("SELECT id FROM genres WHERE LOWER(name) = LOWER(%s)", (body.name,)).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail="Genre already exists")
    cur = db.execute(
        "INSERT INTO genres (name, name_id, bidang_id) VALUES (%s, %s, %s) RETURNING id",
        (body.name, body.name_id, body.bidang_id),
    )
    new_id = cur.fetchone()["id"]
    db.commit()
    row = db.execute(_GENRE_WITH_BIDANG + " WHERE g.id = %s", (new_id,)).fetchone()
    return dict(row)


@router.patch("/{genre_id}", response_model=GenreOut)
def update_genre(genre_id: int, body: GenreCreate, db = Depends(get_db), _=Depends(require_admin)):
    row = db.execute("SELECT * FROM genres WHERE id = %s", (genre_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Genre not found")
    conflict = db.execute(
        "SELECT id FROM genres WHERE LOWER(name) = LOWER(%s) AND id != %s", (body.name, genre_id)
    ).fetchone()
    if conflict:
        raise HTTPException(status_code=400, detail="Genre name already exists")
    db.execute(
        "UPDATE genres SET name = %s, name_id = %s, bidang_id = %s WHERE id = %s",
        (body.name, body.name_id, body.bidang_id, genre_id),
    )
    db.commit()
    row = db.execute(_GENRE_WITH_BIDANG + " WHERE g.id = %s", (genre_id,)).fetchone()
    return dict(row)


@router.delete("/{genre_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_genre(genre_id: int, db = Depends(get_db), _=Depends(require_admin)):
    row = db.execute("SELECT id FROM genres WHERE id = %s", (genre_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Genre not found")
    db.execute("DELETE FROM genres WHERE id = %s", (genre_id,))
    db.commit()
