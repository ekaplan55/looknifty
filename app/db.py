from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "looknifty.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    sub_category TEXT NOT NULL,
    title TEXT NOT NULL,
    brand TEXT NOT NULL,
    segment TEXT NOT NULL,
    current_price REAL NOT NULL,
    image_url TEXT NOT NULL,
    affiliate_url TEXT NOT NULL,
    in_stock INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    price REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    target_url TEXT NOT NULL,
    clicked_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS catalog_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    inserted_count INTEGER NOT NULL,
    updated_count INTEGER NOT NULL,
    unchanged_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    finished_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(products)")}
        if "external_id" not in cols:
            conn.execute("ALTER TABLE products ADD COLUMN external_id TEXT")
        if "source" not in cols:
            conn.execute("ALTER TABLE products ADD COLUMN source TEXT NOT NULL DEFAULT 'seed'")
        if "currency" not in cols:
            conn.execute("ALTER TABLE products ADD COLUMN currency TEXT NOT NULL DEFAULT 'TRY'")
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_products_external_id
            ON products(external_id)
            WHERE external_id IS NOT NULL AND external_id != ''
            """
        )
        conn.commit()


def fetch_products() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM products WHERE in_stock = 1").fetchall()
        return [dict(r) for r in rows]


def latest_previous_price(product_id: int) -> float | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT price FROM price_history
            WHERE product_id = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1 OFFSET 1
            """,
            (product_id,),
        ).fetchone()
        if row:
            return float(row["price"])
        row = conn.execute(
            """
            SELECT price FROM price_history
            WHERE product_id = ?
            ORDER BY recorded_at ASC, id ASC
            LIMIT 1
            """,
            (product_id,),
        ).fetchone()
        return float(row["price"]) if row else None


def apply_catalog_item(item: dict, recorded_at: str) -> str:
    """Insert or update a feed row. Returns inserted, updated, or unchanged."""
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM products WHERE external_id = ?",
            (item["external_id"],),
        ).fetchone()
        if existing is None:
            cur = conn.execute(
                """
                INSERT INTO products (
                    category, sub_category, title, brand, segment, current_price,
                    image_url, affiliate_url, in_stock, description,
                    external_id, source, currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["category"],
                    item["sub_category"],
                    item["title"],
                    item["brand"],
                    item["segment"],
                    item["current_price"],
                    item["image_url"],
                    item["affiliate_url"],
                    1 if item["in_stock"] else 0,
                    item["description"],
                    item["external_id"],
                    item["source"],
                    item["currency"],
                ),
            )
            conn.execute(
                "INSERT INTO price_history (product_id, price, recorded_at) VALUES (?, ?, ?)",
                (cur.lastrowid, item["current_price"], recorded_at),
            )
            conn.commit()
            return "inserted"
        price_changed = abs(float(existing["current_price"]) - float(item["current_price"])) >= 0.01
        same_stock = bool(existing["in_stock"]) == bool(item["in_stock"])
        unchanged = (
            not price_changed
            and same_stock
            and existing["title"] == item["title"]
            and existing["affiliate_url"] == item["affiliate_url"]
        )
        if unchanged:
            return "unchanged"
        conn.execute(
            """
            UPDATE products SET
                category = ?, sub_category = ?, title = ?, brand = ?, segment = ?,
                current_price = ?, image_url = ?, affiliate_url = ?, in_stock = ?,
                description = ?, source = ?, currency = ?
            WHERE id = ?
            """,
            (
                item["category"],
                item["sub_category"],
                item["title"],
                item["brand"],
                item["segment"],
                item["current_price"],
                item["image_url"],
                item["affiliate_url"],
                1 if item["in_stock"] else 0,
                item["description"],
                item["source"],
                item["currency"],
                existing["id"],
            ),
        )
        if price_changed:
            history_count = conn.execute(
                "SELECT COUNT(*) AS c FROM price_history WHERE product_id = ?",
                (existing["id"],),
            ).fetchone()["c"]
            if history_count == 0:
                conn.execute(
                    "INSERT INTO price_history (product_id, price, recorded_at) VALUES (?, ?, ?)",
                    (existing["id"], existing["current_price"], "1970-01-01T00:00:00+00:00"),
                )
            conn.execute(
                "INSERT INTO price_history (product_id, price, recorded_at) VALUES (?, ?, ?)",
                (existing["id"], item["current_price"], recorded_at),
            )
        conn.commit()
        return "updated"


def record_catalog_run(summary: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO catalog_runs (
                source, inserted_count, updated_count, unchanged_count, skipped_count, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                summary["source"],
                summary["inserted"],
                summary["updated"],
                summary["unchanged"],
                summary["skipped"],
                summary["finished_at"],
            ),
        )
        conn.commit()


def catalog_summary() -> dict:
    with connect() as conn:
        product_count = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
        in_stock = conn.execute(
            "SELECT COUNT(*) AS c FROM products WHERE in_stock = 1"
        ).fetchone()["c"]
        run = conn.execute(
            "SELECT * FROM catalog_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    drops = 0
    for product in fetch_products():
        previous = latest_previous_price(product["id"])
        if previous is not None and previous > float(product["current_price"]):
            drops += 1
    return {
        "products": product_count,
        "in_stock": in_stock,
        "price_drops": drops,
        "last_run": dict(run) if run else None,
    }


def get_product(product_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return dict(row) if row else None


def record_click(product_id: int, target_url: str, clicked_at: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO clicks (product_id, target_url, clicked_at) VALUES (?, ?, ?)",
            (product_id, target_url, clicked_at),
        )
        conn.commit()


def commerce_summary() -> dict:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM clicks").fetchone()["c"]
        rows = conn.execute(
            """
            SELECT p.id, p.title, p.brand, COUNT(c.id) AS clicks
            FROM clicks c
            JOIN products p ON p.id = c.product_id
            GROUP BY p.id
            ORDER BY clicks DESC, p.id ASC
            LIMIT 5
            """
        ).fetchall()
    return {
        "clicks": total,
        "top": [dict(row) for row in rows],
    }
