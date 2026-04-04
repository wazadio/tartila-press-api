from fastapi import APIRouter, Depends, HTTPException, status
from app.database import get_db
from app.schemas import PackageCreate, PackageUpdate, PackageOut
from app.auth import require_admin

router = APIRouter(prefix="/packages", tags=["packages"])


def _row_to_out(row) -> dict:
    d = dict(row)
    discount = d.get("discount", 0)
    d["final_price"] = round(d["price"] * (1 - discount / 100))
    return d


@router.get("/", response_model=list[PackageOut])
def list_packages(db=Depends(get_db)):
    rows = db.execute("SELECT * FROM packages ORDER BY type, id").fetchall()
    return [_row_to_out(r) for r in rows]


@router.get("/{package_id}", response_model=PackageOut)
def get_package(package_id: int, db=Depends(get_db)):
    row = db.execute("SELECT * FROM packages WHERE id = %s", (package_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package not found")
    return _row_to_out(row)


@router.post("/", response_model=PackageOut, status_code=status.HTTP_201_CREATED)
def create_package(body: PackageCreate, db=Depends(get_db), _=Depends(require_admin)):
    cur = db.execute(
        "INSERT INTO packages (name, type, description, price, discount) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (body.name, body.type, body.description, body.price, body.discount),
    )
    new_id = cur.fetchone()["id"]
    db.commit()
    row = db.execute("SELECT * FROM packages WHERE id = %s", (new_id,)).fetchone()
    return _row_to_out(row)


@router.patch("/{package_id}", response_model=PackageOut)
def update_package(package_id: int, body: PackageUpdate, db=Depends(get_db), _=Depends(require_admin)):
    row = db.execute("SELECT * FROM packages WHERE id = %s", (package_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package not found")

    data = dict(row)
    updates = body.model_dump(exclude_unset=True)
    data.update(updates)

    db.execute(
        "UPDATE packages SET name=%s, type=%s, description=%s, price=%s, discount=%s WHERE id=%s",
        (data["name"], data["type"], data["description"], data["price"], data["discount"], package_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM packages WHERE id = %s", (package_id,)).fetchone()
    return _row_to_out(row)


@router.delete("/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_package(package_id: int, db=Depends(get_db), _=Depends(require_admin)):
    row = db.execute("SELECT id FROM packages WHERE id = %s", (package_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package not found")
    db.execute("DELETE FROM packages WHERE id = %s", (package_id,))
    db.commit()
