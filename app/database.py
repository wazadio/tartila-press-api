import json
import os
from typing import Generator

import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://tartila:tartila@localhost:5432/tartila",
)


class PGSession:
    """
    Thin wrapper around a psycopg2 connection that exposes a sqlite3-like
    execute() / commit() / close() interface so routers need minimal changes.
    Each call to execute() creates a fresh cursor and returns it directly
    (psycopg2.extras.RealDictCursor), so callers can chain .fetchone() /
    .fetchall() on the result.
    """

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=None):
        cur = self._conn.cursor()
        cur.execute(sql, params or ())
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_db() -> Generator[PGSession, None, None]:
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    session = PGSession(conn)
    try:
        yield session
    finally:
        session.close()


def init_db():
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                  SERIAL PRIMARY KEY,
            name                TEXT    NOT NULL,
            email               TEXT    UNIQUE NOT NULL,
            password            TEXT    NOT NULL,
            role                TEXT    NOT NULL DEFAULT 'user',
            is_verified         BOOLEAN NOT NULL DEFAULT FALSE,
            verification_token  TEXT,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS authors (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER UNIQUE REFERENCES users(id) ON DELETE SET NULL,
            name            TEXT NOT NULL,
            photo           TEXT,
            bio             TEXT,
            nationality     TEXT,
            books_published INTEGER DEFAULT 0,
            genres          TEXT DEFAULT '[]',
            website         TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id             SERIAL PRIMARY KEY,
            title          TEXT    NOT NULL,
            author_id      INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
            cover          TEXT,
            genre          TEXT    NOT NULL,
            published_year INTEGER,
            pages          INTEGER,
            isbn           TEXT,
            description    TEXT,
            price          INTEGER DEFAULT 0,
            rating         REAL    DEFAULT 0,
            featured       BOOLEAN DEFAULT FALSE,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS genres (
            id         SERIAL PRIMARY KEY,
            name       TEXT UNIQUE NOT NULL,
            name_id    TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS packages (
            id          SERIAL PRIMARY KEY,
            name        TEXT    NOT NULL,
            type        TEXT    NOT NULL CHECK(type IN ('per_chapter', 'per_book')),
            description TEXT,
            price       INTEGER NOT NULL DEFAULT 0,
            discount    INTEGER NOT NULL DEFAULT 0 CHECK(discount >= 0 AND discount <= 100),
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id                SERIAL PRIMARY KEY,
            user_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
            package_id        INTEGER REFERENCES packages(id) ON DELETE SET NULL,
            package_name      TEXT NOT NULL,
            package_type      TEXT NOT NULL CHECK(package_type IN ('per_chapter', 'per_book')),
            unit_price        INTEGER NOT NULL,
            chapters          INTEGER NOT NULL DEFAULT 1,
            total_amount      INTEGER NOT NULL,
            book_title        TEXT NOT NULL,
            genre             TEXT NOT NULL,
            customer_name     TEXT NOT NULL,
            customer_email    TEXT NOT NULL,
            customer_phone    TEXT NOT NULL,
            notes             TEXT,
            status            TEXT NOT NULL DEFAULT 'unpaid' CHECK(status IN ('paid', 'unpaid')),
            delivery_deadline TEXT,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS book_chapters (
            id         SERIAL PRIMARY KEY,
            book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            number     INTEGER NOT NULL,
            title      TEXT    NOT NULL,
            price      INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (book_id, number)
        )
    """)

    # Idempotent column migrations
    cur.execute("""
        ALTER TABLE authors
        ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
    """)
    cur.execute("ALTER TABLE genres ADD COLUMN IF NOT EXISTS name_id TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS delivery_deadline TEXT")
    cur.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS is_template BOOLEAN DEFAULT FALSE")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bidang (
            id   SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        ALTER TABLE books
        ADD COLUMN IF NOT EXISTS bidang_id INTEGER REFERENCES bidang(id) ON DELETE SET NULL
    """)
    # drop old free-text bidang column if it still exists
    cur.execute("ALTER TABLE books DROP COLUMN IF EXISTS bidang")
    cur.execute("""
        ALTER TABLE genres
        ADD COLUMN IF NOT EXISTS bidang_id INTEGER REFERENCES bidang(id) ON DELETE SET NULL
    """)
    cur.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS synopsis TEXT")
    # Admin-verified flag for authors: TRUE = visible in public listing
    cur.execute("""
        ALTER TABLE authors
        ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE
    """)
    # Existing authors created directly by admin should be visible by default
    cur.execute("""
        UPDATE authors SET is_verified = TRUE WHERE user_id IS NULL AND is_verified = FALSE
    """)
    # Stock quota per book and per chapter
    cur.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT NULL")
    cur.execute("ALTER TABLE book_chapters ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT NULL")
    # Store which book/chapters were selected in per-chapter transactions for stock tracking
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS book_id INTEGER REFERENCES books(id) ON DELETE SET NULL")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS chapter_ids TEXT NOT NULL DEFAULT '[]'")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS stock_exhausted BOOLEAN NOT NULL DEFAULT FALSE")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS transaction_type TEXT NOT NULL DEFAULT 'publishing'")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS address TEXT")
    cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS manuscript_files TEXT NOT NULL DEFAULT '[]'")
    cur.execute("ALTER TABLE packages ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE packages ADD COLUMN IF NOT EXISTS is_featured BOOLEAN NOT NULL DEFAULT FALSE")

    conn.autocommit = False
    _seed(conn)
    _seed_genres(conn)
    _seed_packages(conn)
    conn.close()


# ── Seed helpers ──────────────────────────────────────────────────────────────

def _seed(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM authors")
    if cur.fetchone()["n"] > 0:
        return

    authors = [
        (
            "Ahmad Fuad",
            "https://placehold.co/200x200?text=AF",
            "Ahmad Fuad is an award-winning novelist known for his poetic prose and exploration of Indonesian cultural identity. He has published over fifteen books and received multiple national literary awards.",
            "Indonesian", 6,
            json.dumps(["Literary Fiction", "Historical Fiction"]),
            "https://example.com/ahmad-fuad",
        ),
        (
            "Siti Rahma",
            "https://placehold.co/200x200?text=SR",
            "Siti Rahma is a bestselling author of children's literature and young adult fiction. Her works are beloved for their warmth, humor, and relatable characters.",
            "Indonesian", 9,
            json.dumps(["Children's Literature", "Young Adult"]),
            "https://example.com/siti-rahma",
        ),
        (
            "Budi Santoso",
            "https://placehold.co/200x200?text=BS",
            "Budi Santoso writes gripping thrillers and mystery novels set across Southeast Asia. A former journalist, his writing blends detailed research with fast-paced narrative.",
            "Indonesian", 5,
            json.dumps(["Thriller", "Mystery"]),
            "https://example.com/budi-santoso",
        ),
        (
            "Dewi Kartika",
            "https://placehold.co/200x200?text=DK",
            "Dewi Kartika is a poet and essayist whose work explores themes of feminism, spirituality, and modern Indonesian life. She is a prominent voice in contemporary Indonesian literature.",
            "Indonesian", 4,
            json.dumps(["Poetry", "Essays"]),
            "https://example.com/dewi-kartika",
        ),
    ]
    cur.executemany(
        "INSERT INTO authors (name, photo, bio, nationality, books_published, genres, website)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s)",
        authors,
    )

    books = [
        ("Jejak di Tanah Merah", 1, "https://placehold.co/300x420?text=Jejak+di+Tanah+Merah",
         "Historical Fiction", 2022, 348, "978-602-1234-01-1",
         "A sweeping historical novel that traces three generations of a Javanese family from the colonial era to independence. Rich with local color and emotional depth, this book is a celebration of Indonesian resilience.",
         89000, 4.7, True),
        ("Bintang Kecil", 2, "https://placehold.co/300x420?text=Bintang+Kecil",
         "Children's Literature", 2023, 120, "978-602-1234-02-8",
         "A heartwarming story about a young girl named Nisa who discovers she has the power to grant small wishes using nothing but kindness and imagination.",
         59000, 4.9, True),
        ("Bayangan di Kota Lama", 3, "https://placehold.co/300x420?text=Bayangan+di+Kota+Lama",
         "Mystery", 2021, 412, "978-602-1234-03-5",
         "A detective thriller set in the old quarters of Semarang. When a series of mysterious disappearances rock the city, journalist-turned-detective Arif must untangle a web of secrets buried in colonial history.",
         95000, 4.5, True),
        ("Puisi untuk Ibu", 4, "https://placehold.co/300x420?text=Puisi+untuk+Ibu",
         "Poetry", 2023, 96, "978-602-1234-04-2",
         "A collection of poems dedicated to mothers everywhere. Written with tenderness and honesty, Dewi Kartika explores the complex, beautiful bond between parent and child.",
         75000, 4.8, False),
        ("Langit Senja di Timur", 1, "https://placehold.co/300x420?text=Langit+Senja+di+Timur",
         "Literary Fiction", 2020, 286, "978-602-1234-05-9",
         "A contemplative literary novel following a man's journey across eastern Indonesia, confronting questions of faith, modernity, and belonging.",
         85000, 4.4, False),
        ("Si Kancil dan Robot", 2, "https://placehold.co/300x420?text=Si+Kancil+dan+Robot",
         "Children's Literature", 2022, 88, "978-602-1234-06-6",
         "The classic trickster mouse-deer Kancil is back — but this time he teams up with a bumbling robot to outsmart a greedy landlord. Hilarious and full of heart.",
         55000, 4.6, False),
    ]
    cur.executemany(
        "INSERT INTO books"
        " (title, author_id, cover, genre, published_year, pages, isbn, description, price, rating, featured)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        books,
    )
    conn.commit()


def _seed_genres(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM genres")
    if cur.fetchone()["n"] > 0:
        return
    genres = [
        ("Literary Fiction", "Fiksi Sastra"),
        ("Historical Fiction", "Fiksi Sejarah"),
        ("Mystery", "Misteri"),
        ("Thriller", "Thriller"),
        ("Romance", "Romansa"),
        ("Horror", "Horor"),
        ("Science Fiction", "Fiksi Ilmiah"),
        ("Fantasy", "Fantasi"),
        ("Children's Literature", "Sastra Anak"),
        ("Young Adult", "Remaja"),
        ("Poetry", "Puisi"),
        ("Essays", "Esai"),
        ("Biography", "Biografi"),
        ("Short Stories", "Cerpen"),
    ]
    cur.executemany("INSERT INTO genres (name, name_id) VALUES (%s, %s)", genres)
    conn.commit()


def _seed_packages(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM packages")
    if cur.fetchone()["n"] > 0:
        return
    packages = [
        (
            "Per Chapter Publishing", "per_chapter",
            "Publish your book chapter by chapter. Ideal for serialized content or authors who prefer a flexible, pay-as-you-go approach. Each chapter is professionally formatted, reviewed, and published on our platform.",
            75000, 0,
        ),
        (
            "Full Book Publishing", "per_book",
            "Publish your complete manuscript as a single book. Includes full editorial review, professional formatting, cover design consultation, and permanent listing on Tartila Press. Best value for complete works.",
            500000, 15,
        ),
    ]
    cur.executemany(
        "INSERT INTO packages (name, type, description, price, discount) VALUES (%s,%s,%s,%s,%s)",
        packages,
    )
    conn.commit()
