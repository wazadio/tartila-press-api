from datetime import datetime, date
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Literal


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ── Author ────────────────────────────────────────────────────────────────────

class AuthorBase(BaseModel):
    name: str
    photo: Optional[str] = None
    bio: Optional[str] = None
    nationality: Optional[str] = None
    books_published: Optional[int] = 0
    genres: Optional[List[str]] = []
    website: Optional[str] = None


class AuthorCreate(AuthorBase):
    pass


class AuthorUpdate(AuthorBase):
    name: Optional[str] = None


class AuthorOut(AuthorBase):
    id: int
    is_verified: bool = False

    class Config:
        from_attributes = True


# ── Book ──────────────────────────────────────────────────────────────────────

class BookBase(BaseModel):
    title: str
    author_id: int
    cover: Optional[str] = None
    genre: str
    published_year: Optional[int] = None
    pages: Optional[int] = None
    isbn: Optional[str] = None
    description: Optional[str] = None
    synopsis: Optional[str] = None
    price: Optional[int] = 0
    rating: Optional[float] = 0.0
    featured: Optional[bool] = False
    is_template: Optional[bool] = False
    bidang_id: Optional[int] = None
    stock: Optional[int] = None


class BookCreate(BookBase):
    pass


class BookUpdate(BookBase):
    title: Optional[str] = None
    author_id: Optional[int] = None
    genre: Optional[str] = None


class BookOut(BookBase):
    id: int
    author: Optional[str] = None       # denormalized author name
    bidang_name: Optional[str] = None  # denormalized bidang name

    class Config:
        from_attributes = True


# ── Bidang ───────────────────────────────────────────────────────────────────

class BidangCreate(BaseModel):
    name: str


class BidangOut(BidangCreate):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Package ───────────────────────────────────────────────────────────────────

class PackageBase(BaseModel):
    name: str
    type: Literal["per_chapter", "per_book"]
    description: Optional[str] = None
    price: int
    discount: int = 0

    @field_validator("discount")
    @classmethod
    def discount_range(cls, v):
        if not 0 <= v <= 100:
            raise ValueError("discount must be between 0 and 100")
        return v


class PackageCreate(PackageBase):
    pass


class PackageUpdate(PackageBase):
    name: Optional[str] = None
    type: Optional[Literal["per_chapter", "per_book"]] = None
    price: Optional[int] = None
    discount: Optional[int] = None


class PackageOut(PackageBase):
    id: int
    final_price: int

    class Config:
        from_attributes = True


# ── Genre ────────────────────────────────────────────────────────────────────

class GenreBase(BaseModel):
    name: str
    name_id: Optional[str] = None
    bidang_id: Optional[int] = None


class GenreCreate(GenreBase):
    pass


class GenreOut(GenreBase):
    id: int
    bidang_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Writer ────────────────────────────────────────────────────────────────────

class WriterRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class WriterOut(AuthorBase):
    id: int
    user_id: int
    email: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WriterUpdate(BaseModel):
    name: Optional[str] = None
    photo: Optional[str] = None
    bio: Optional[str] = None
    nationality: Optional[str] = None
    genres: Optional[List[str]] = None
    website: Optional[str] = None


# ── Transaction ───────────────────────────────────────────────────────────────

class TransactionCreate(BaseModel):
    package_id: int
    book_title: str
    genre: str
    chapters: Optional[int] = 1
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
    notes: Optional[str] = None
    book_id: Optional[int] = None
    chapter_ids: Optional[List[int]] = []


class TransactionOut(BaseModel):
    id: int
    user_id: Optional[int] = None
    user_role: Optional[str] = None
    user_is_verified: Optional[bool] = None
    package_id: Optional[int] = None
    package_name: str
    package_type: Literal["per_chapter", "per_book"]
    unit_price: int
    chapters: int
    total_amount: int
    book_title: str
    genre: str
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
    notes: Optional[str] = None
    status: Literal["paid", "unpaid"]
    delivery_deadline: Optional[date] = None
    bank_name: str
    bank_account_name: str
    bank_account_number: str
    created_at: Optional[datetime] = None
    book_id: Optional[int] = None
    chapter_ids: Optional[List[int]] = []
    stock_exhausted: bool = False

    class Config:
        from_attributes = True


class PaymentConfigOut(BaseModel):
    bank_name: str
    bank_account_name: str
    bank_account_number: str


class TransactionUpdate(BaseModel):
    status: Optional[Literal["paid", "unpaid"]] = None
    delivery_deadline: Optional[str] = None


# ── Book Chapters ─────────────────────────────────────────────────────────────

class BookChapterBase(BaseModel):
    number: int
    title: str
    price: int = 0
    stock: Optional[int] = None


class BookChapterCreate(BookChapterBase):
    pass


class BookChapterOut(BookChapterBase):
    id: int
    book_id: int

    class Config:
        from_attributes = True
