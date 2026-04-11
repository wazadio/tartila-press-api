from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_admin
from app.database import get_db
from app.schemas import BidangCreate, BidangOut

router = APIRouter(prefix="/bidang", tags=["bidang"])


@router.get("", response_model=list[BidangOut])
def list_bidang(db=Depends(get_db)):
    rows = db.execute("SELECT * FROM bidang ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@router.post("", response_model=BidangOut, status_code=status.HTTP_201_CREATED)
def create_bidang(body: BidangCreate, db=Depends(get_db), _=Depends(require_admin)):
    existing = db.execute(
        "SELECT id FROM bidang WHERE LOWER(name) = LOWER(%s)", (body.name,)
    ).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail="Bidang already exists")
    cur = db.execute("INSERT INTO bidang (name) VALUES (%s) RETURNING id", (body.name,))
    new_id = cur.fetchone()["id"]
    db.commit()
    row = db.execute("SELECT * FROM bidang WHERE id = %s", (new_id,)).fetchone()
    return dict(row)


@router.patch("/{bidang_id}", response_model=BidangOut)
def update_bidang(bidang_id: int, body: BidangCreate, db=Depends(get_db), _=Depends(require_admin)):
    row = db.execute("SELECT * FROM bidang WHERE id = %s", (bidang_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Bidang not found")
    conflict = db.execute(
        "SELECT id FROM bidang WHERE LOWER(name) = LOWER(%s) AND id != %s", (body.name, bidang_id)
    ).fetchone()
    if conflict:
        raise HTTPException(status_code=400, detail="Bidang name already exists")
    db.execute("UPDATE bidang SET name = %s WHERE id = %s", (body.name, bidang_id))
    db.commit()
    row = db.execute("SELECT * FROM bidang WHERE id = %s", (bidang_id,)).fetchone()
    return dict(row)


@router.delete("/{bidang_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bidang(bidang_id: int, db=Depends(get_db), _=Depends(require_admin)):
    row = db.execute("SELECT id FROM bidang WHERE id = %s", (bidang_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Bidang not found")
    db.execute("DELETE FROM bidang WHERE id = %s", (bidang_id,))
    db.commit()
