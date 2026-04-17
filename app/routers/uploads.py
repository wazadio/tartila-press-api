import io
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import JSONResponse

from app.auth import require_writer

UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_KTP_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_KTP_TYPES_WITH_PDF = ALLOWED_KTP_TYPES | {"application/pdf"}
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


# ── KTP ───────────────────────────────────────────────────────────────────────

MAX_KTP_MB = 5


def _extract_ktp_text(image_bytes: bytes) -> dict:
    """OCR a KTP image and return extracted field values. Gracefully returns {} on failure."""
    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        if w < 1000:
            img = img.resize((w * 2, h * 2), Image.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = img.filter(ImageFilter.SHARPEN)
        text = pytesseract.image_to_string(img, lang="ind+eng", config="--psm 6")
    except Exception:
        return {}

    result = {}

    nik_m = re.search(r"\b(\d{16})\b", text)
    if nik_m:
        result["nik"] = nik_m.group(1)

    nama_m = re.search(r"(?:NAMA|Nama)\s*:?\s*([A-Z][A-Z\s'.,/-]{2,60})", text)
    if nama_m:
        result["creator_name"] = nama_m.group(1).strip()

    if re.search(r"LAKI.LAKI", text, re.IGNORECASE):
        result["gender"] = "LAKI-LAKI"
    elif re.search(r"PEREMPUAN", text, re.IGNORECASE):
        result["gender"] = "PEREMPUAN"

    alamat_m = re.search(r"(?:ALAMAT|Alamat)\s*:?\s*([^\n]{4,})", text, re.IGNORECASE)
    if alamat_m:
        result["address"] = alamat_m.group(1).strip()

    kec_m = re.search(r"(?:KECAMATAN|Kecamatan)\s*:?\s*([A-Za-z\s]+)", text, re.IGNORECASE)
    if kec_m:
        result["district"] = kec_m.group(1).strip()

    return result


@router.post("/ktp-upload", status_code=status.HTTP_201_CREATED)
async def upload_ktp(
    file: UploadFile = File(...),
    _=Depends(require_writer),
):
    """Store KTP file (PNG/JPG/PDF) and return its URL."""
    if file.content_type not in ALLOWED_KTP_TYPES_WITH_PDF:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Hanya PNG, JPG, atau PDF yang diperbolehkan untuk Foto KTP.",
        )
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="File kosong.")
    if len(contents) > MAX_KTP_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Ukuran file KTP maksimal {MAX_KTP_MB} MB.",
        )
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    filename = f"ktp_{uuid.uuid4().hex}.{ext}"
    (UPLOADS_DIR / filename).write_bytes(contents)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"url": f"/uploads/{filename}", "filename": filename},
    )


@router.post("/ktp-ocr")
async def ocr_ktp(
    file: UploadFile = File(...),
    _=Depends(require_writer),
):
    """Upload a KTP image (PNG/JPG) and return OCR-extracted field values."""
    if file.content_type not in ALLOWED_KTP_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="OCR hanya mendukung PNG atau JPG.",
        )
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="File kosong.")
    if len(contents) > MAX_KTP_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Ukuran file KTP maksimal {MAX_KTP_MB} MB.",
        )
    extracted = _extract_ktp_text(contents)
    return {"extracted": extracted}
