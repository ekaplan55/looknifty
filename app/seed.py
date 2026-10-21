from __future__ import annotations

from app.db import connect, init_db

AFF = "looknifty_01"

EXTERNAL_IDS = {
    "Brunello Krem Kaşmir Polo": "brunello-krem-polo",
    "Mango Krem Pamuk Polo": "mango-krem-polo",
    "LCW Krem Pike Polo": "lcw-krem-polo",
    "Loro Piana Lacivert Chino": "loro-piana-chino",
    "Zara Lacivert Slim Chino": "zara-lacivert-chino",
    "LCW Lacivert Chino": "lcw-lacivert-chino",
    "Common Projects Beyaz Deri Sneaker": "common-projects-sneaker",
    "Adidas Stan Smith Beyaz": "adidas-stan-smith",
    "LCW Beyaz Düz Taban Ayakkabı": "lcw-beyaz-sneaker",
}

PRODUCTS = [
    # Üst Giyim / Triko Polo
    (
        "Üst Giyim",
        "Triko Polo",
        "Brunello Krem Kaşmir Polo",
        "Brunello",
        "Lüks",
        12990.0,
        "https://images.unsplash.com/photo-1618354691373-d851c5c3a99b?w=600",
        f"https://example.com/polo-luxe?aff_id={AFF}",
        1,
        "Krem rengi kaşmir triko polo tişört smart casual",
    ),
    (
        "Üst Giyim",
        "Triko Polo",
        "Mango Krem Pamuk Polo",
        "Mango",
        "Ulaşılabilir",
        1499.0,
        "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=600",
        f"https://example.com/polo-mid?aff_id={AFF}",
        1,
        "Krem pamuklu triko polo tişört günlük şık",
    ),
    (
        "Üst Giyim",
        "Triko Polo",
        "LCW Krem Pike Polo",
        "LCW",
        "Ekonomik",
        399.9,
        "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=600",
        f"https://example.com/polo-eco?aff_id={AFF}",
        1,
        "Krem rengi pamuklu pike polo tişört",
    ),
    # Alt Giyim / Chino
    (
        "Alt Giyim",
        "Chino Pantolon",
        "Loro Piana Lacivert Chino",
        "Loro Piana",
        "Lüks",
        18900.0,
        "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=600",
        f"https://example.com/chino-luxe?aff_id={AFF}",
        1,
        "Lacivert pamuklu slim chino pantolon lüks",
    ),
    (
        "Alt Giyim",
        "Chino Pantolon",
        "Zara Lacivert Slim Chino",
        "Zara",
        "Ulaşılabilir",
        1290.0,
        "https://images.unsplash.com/photo-1624378439575-d2c3c7f0c4b9?w=600",
        f"https://example.com/chino-mid?aff_id={AFF}",
        1,
        "Lacivert pamuklu chino pantolon smart casual",
    ),
    (
        "Alt Giyim",
        "Chino Pantolon",
        "LCW Lacivert Chino",
        "LCW",
        "Ekonomik",
        549.9,
        "https://images.unsplash.com/photo-1591195853828-11db59a44f6b?w=600",
        f"https://example.com/chino-eco?aff_id={AFF}",
        1,
        "Lacivert pamuklu chino pantolon günlük",
    ),
    # Ayakkabı / Sneaker
    (
        "Ayakkabı",
        "Sneaker",
        "Common Projects Beyaz Deri Sneaker",
        "Common Projects",
        "Lüks",
        21450.0,
        "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=600",
        f"https://example.com/sneaker-luxe?aff_id={AFF}",
        1,
        "Beyaz minimalist deri sneaker",
    ),
    (
        "Ayakkabı",
        "Sneaker",
        "Adidas Stan Smith Beyaz",
        "Adidas",
        "Ulaşılabilir",
        3499.0,
        "https://images.unsplash.com/photo-1560769629-975ec94e6a86?w=600",
        f"https://example.com/sneaker-mid?aff_id={AFF}",
        1,
        "Beyaz klasik deri sneaker minimalist",
    ),
    (
        "Ayakkabı",
        "Sneaker",
        "LCW Beyaz Düz Taban Ayakkabı",
        "LCW",
        "Ekonomik",
        699.9,
        "https://images.unsplash.com/photo-1606107557195-0e29a4b5b4aa?w=600",
        f"https://example.com/sneaker-eco?aff_id={AFF}",
        1,
        "Beyaz düz taban sneaker ekonomik",
    ),
]


def seed() -> None:
    init_db()
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
        if count == 0:
            conn.executemany(
                """
                INSERT INTO products (
                    category, sub_category, title, brand, segment,
                    current_price, image_url, affiliate_url, in_stock, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                PRODUCTS,
            )
            sneaker = conn.execute(
                "SELECT id FROM products WHERE title = ?",
                ("LCW Beyaz Düz Taban Ayakkabı",),
            ).fetchone()
            if sneaker:
                conn.execute(
                    """
                    INSERT INTO price_history (product_id, price, recorded_at)
                    VALUES (?, 849.9, '2026-09-01T00:00:00'),
                           (?, 699.9, '2026-10-01T00:00:00')
                    """,
                    (sneaker["id"], sneaker["id"]),
                )
            conn.commit()
        for title, external_id in EXTERNAL_IDS.items():
            conn.execute(
                """
                UPDATE products
                SET external_id = ?, source = COALESCE(source, 'seed')
                WHERE title = ? AND (external_id IS NULL OR external_id = '')
                """,
                (external_id, title),
            )
        conn.commit()


if __name__ == "__main__":
    seed()
    print("Seed complete.")
