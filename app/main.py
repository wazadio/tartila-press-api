from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import auth, books, authors, packages, uploads, oauth, genres, transactions

UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Tartila API", version="1.0.0", redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(auth.router, prefix="/api")
app.include_router(books.router, prefix="/api")
app.include_router(authors.router, prefix="/api")
app.include_router(packages.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(oauth.router, prefix="/api")
app.include_router(genres.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")


@app.get("/")
def root():
    return {"message": "Tartila API is running"}
