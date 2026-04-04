import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "tartila.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT    NOT NULL,
            email               TEXT    UNIQUE NOT NULL,
            password            TEXT    NOT NULL,
            role                TEXT    NOT NULL DEFAULT 'user',
            is_verified         INTEGER NOT NULL DEFAULT 0,
            verification_token  TEXT,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS authors (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER UNIQUE REFERENCES users(id) ON DELETE SET NULL,
            name            TEXT NOT NULL,
            photo           TEXT,
            bio             TEXT,
            nationality     TEXT,
            books_published INTEGER DEFAULT 0,
            genres          TEXT DEFAULT '[]',
            website         TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS books (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
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
            featured       INTEGER DEFAULT 0,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS genres (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE NOT NULL,
            name_id    TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS packages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            type        TEXT    NOT NULL CHECK(type IN ('per_chapter', 'per_book')),
            description TEXT,
            price       INTEGER NOT NULL DEFAULT 0,
            discount    INTEGER NOT NULL DEFAULT 0 CHECK(discount >= 0 AND discount <= 100),
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER REFERENCES users(id) ON DELETE SET NULL,
            package_id          INTEGER REFERENCES packages(id) ON DELETE SET NULL,
            package_name        TEXT NOT NULL,
            package_type        TEXT NOT NULL CHECK(package_type IN ('per_chapter', 'per_book')),
            unit_price          INTEGER NOT NULL,
            chapters            INTEGER NOT NULL DEFAULT 1,
            total_amount        INTEGER NOT NULL,
            book_title          TEXT NOT NULL,
            genre               TEXT NOT NULL,
            customer_name       TEXT NOT NULL,
            customer_email      TEXT NOT NULL,
            customer_phone      TEXT NOT NULL,
            notes               TEXT,
            status              TEXT NOT NULL DEFAULT 'unpaid' CHECK(status IN ('paid', 'unpaid')),
            delivery_deadline   TEXT,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        );

    """)

    conn.commit()

    # Migrations for existing databases
    try:
        conn.execute("ALTER TABLE authors ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
        conn.commit()
    except Exception:
        pass  # column already exists

    conn.execute("DROP TABLE IF EXISTS writer_profiles")
    conn.commit()

    try:
        conn.execute("ALTER TABLE genres ADD COLUMN name_id TEXT")
        conn.commit()
    except Exception:
        pass  # column already exists

    try:
        conn.execute("ALTER TABLE transactions ADD COLUMN delivery_deadline TEXT")
        conn.commit()
    except Exception:
        pass  # column already exists

    _seed(conn)
    _seed_packages(conn)
    _seed_genres(conn)
    conn.close()


def _seed(conn: sqlite3.Connection):
    cur = conn.cursor()

    # Skip if data already exists
    if cur.execute("SELECT COUNT(*) FROM authors").fetchone()[0] > 0:
        return

    authors = [
        (
            "Ahmad Fuad",
            "https://placehold.co/200x200?text=AF",
            "Ahmad Fuad is an award-winning novelist known for his poetic prose and exploration of Indonesian cultural identity. He has published over fifteen books and received multiple national literary awards.",
            "Indonesian",
            6,
            json.dumps(["Literary Fiction", "Historical Fiction"]),
            "https://example.com/ahmad-fuad",
        ),
        (
            "Siti Rahma",
            "https://placehold.co/200x200?text=SR",
            "Siti Rahma is a bestselling author of children's literature and young adult fiction. Her works are beloved for their warmth, humor, and relatable characters.",
            "Indonesian",
            9,
            json.dumps(["Children's Literature", "Young Adult"]),
            "https://example.com/siti-rahma",
        ),
        (
            "Budi Santoso",
            "https://placehold.co/200x200?text=BS",
            "Budi Santoso writes gripping thrillers and mystery novels set across Southeast Asia. A former journalist, his writing blends detailed research with fast-paced narrative.",
            "Indonesian",
            5,
            json.dumps(["Thriller", "Mystery"]),
            "https://example.com/budi-santoso",
        ),
        (
            "Dewi Kartika",
            "https://placehold.co/200x200?text=DK",
            "Dewi Kartika is a poet and essayist whose work explores themes of feminism, spirituality, and modern Indonesian life. She is a prominent voice in contemporary Indonesian literature.",
            "Indonesian",
            4,
            json.dumps(["Poetry", "Essays"]),
            "https://example.com/dewi-kartika",
        ),
    ]
    cur.executemany(
        "INSERT INTO authors (name, photo, bio, nationality, books_published, genres, website) VALUES (?,?,?,?,?,?,?)",
        authors,
    )

    books = [
        (
            "Jejak di Tanah Merah", 1,
            "https://placehold.co/300x420?text=Jejak+di+Tanah+Merah",
            "Historical Fiction", 2022, 348, "978-602-1234-01-1",
            "A sweeping historical novel that traces three generations of a Javanese family from the colonial era to independence. Rich with local color and emotional depth, this book is a celebration of Indonesian resilience.",
            89000, 4.7, 1,
        ),
        (
            "Bintang Kecil", 2,
            "https://placehold.co/300x420?text=Bintang+Kecil",
            "Children's Literature", 2023, 120, "978-602-1234-02-8",
            "A heartwarming story about a young girl named Nisa who discovers she has the power to grant small wishes using nothing but kindness and imagination.",
            59000, 4.9, 1,
        ),
        (
            "Bayangan di Kota Lama", 3,
            "https://placehold.co/300x420?text=Bayangan+di+Kota+Lama",
            "Mystery", 2021, 412, "978-602-1234-03-5",
            "A detective thriller set in the old quarters of Semarang. When a series of mysterious disappearances rock the city, journalist-turned-detective Arif must untangle a web of secrets buried in colonial history.",
            95000, 4.5, 1,
        ),
        (
            "Puisi untuk Ibu", 4,
            "https://placehold.co/300x420?text=Puisi+untuk+Ibu",
            "Poetry", 2023, 96, "978-602-1234-04-2",
            "A collection of poems dedicated to mothers everywhere. Written with tenderness and honesty, Dewi Kartika explores the complex, beautiful bond between parent and child.",
            75000, 4.8, 0,
        ),
        (
            "Langit Senja di Timur", 1,
            "https://placehold.co/300x420?text=Langit+Senja+di+Timur",
            "Literary Fiction", 2020, 286, "978-602-1234-05-9",
            "A contemplative literary novel following a man's journey across eastern Indonesia, confronting questions of faith, modernity, and belonging.",
            85000, 4.4, 0,
        ),
        (
            "Si Kancil dan Robot", 2,
            "https://placehold.co/300x420?text=Si+Kancil+dan+Robot",
            "Children's Literature", 2022, 88, "978-602-1234-06-6",
            "The classic trickster mouse-deer Kancil is back — but this time he teams up with a bumbling robot to outsmart a greedy landlord. Hilarious and full of heart.",
            55000, 4.6, 0,
        ),
    ]
    cur.executemany(
        """INSERT INTO books
           (title, author_id, cover, genre, published_year, pages, isbn, description, price, rating, featured)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        books,
    )

    conn.commit()


def _seed_genres(conn: sqlite3.Connection):
    cur = conn.cursor()
    if cur.execute("SELECT COUNT(*) FROM genres").fetchone()[0] > 0:
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
    cur.executemany("INSERT INTO genres (name, name_id) VALUES (?, ?)", genres)
    conn.commit()


def _seed_packages(conn: sqlite3.Connection):
    cur = conn.cursor()
    if cur.execute("SELECT COUNT(*) FROM packages").fetchone()[0] > 0:
        return

    packages = [
        (
            "Per Chapter Publishing",
            "per_chapter",
            "Publish your book chapter by chapter. Ideal for serialized content or authors who prefer a flexible, pay-as-you-go approach. Each chapter is professionally formatted, reviewed, and published on our platform.",
            75000,
            0,
        ),
        (
            "Full Book Publishing",
            "per_book",
            "Publish your complete manuscript as a single book. Includes full editorial review, professional formatting, cover design consultation, and permanent listing on Tartila Press. Best value for complete works.",
            500000,
            15,
        ),
    ]
    cur.executemany(
        "INSERT INTO packages (name, type, description, price, discount) VALUES (?,?,?,?,?)",
        packages,
    )
    conn.commit()
