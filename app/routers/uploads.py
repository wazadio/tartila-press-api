import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import JSONResponse

from app.auth import require_writer

UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_MANUSCRIPT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
ALLOWED_MANUSCRIPT_EXTS = {"pdf", "doc", "docx"}
MAX_IMAGE_MB = 5
MAX_MANUSCRIPT_MB = 20

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/image", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    _=Depends(require_writer),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: jpeg, png, webp, gif.",
        )

    contents = await file.read()
    if len(contents) > MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_IMAGE_MB} MB.",
        )

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    dest = UPLOADS_DIR / filename
    dest.write_bytes(contents)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"url": f"/uploads/{filename}", "filename": filename},
    )


@router.post("/manuscript", status_code=status.HTTP_201_CREATED)
async def upload_manuscript(
    file: UploadFile = File(...),
):
    """
    Accept PDF / DOC / DOCX manuscript uploads for publishing service orders.
    No authentication required — upload happens before the transaction is created.
    """
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    content_type_ok = file.content_type in ALLOWED_MANUSCRIPT_TYPES
    ext_ok = ext in ALLOWED_MANUSCRIPT_EXTS

    if not (content_type_ok or ext_ok):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Hanya file PDF, DOC, atau DOCX yang diperbolehkan.",
        )

    contents = await file.read()
    if len(contents) > MAX_MANUSCRIPT_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Ukuran file terlalu besar. Maksimal {MAX_MANUSCRIPT_MB} MB.",
        )
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="File kosong.")

    safe_original = "".join(
        c if c.isalnum() or c in "-_." else "_"
        for c in (file.filename or "naskah")
    )[:80]
    filename = f"ms_{uuid.uuid4().hex}_{safe_original}"
    dest = UPLOADS_DIR / filename
    dest.write_bytes(contents)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "url": f"/uploads/{filename}",
            "filename": filename,
            "original_name": file.filename or filename,
        },
    )
