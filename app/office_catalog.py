"""Elle doğrulanmış ofis-sonrası katalog.

Segment fiyattan değil, marka listesinden gelir. Listede olmayan marka içeri alınmaz.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.db import apply_catalog_item, connect, init_db

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "catalog" / "office.json"
CATALOG_IMAGES = ROOT / "catalog-images"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

BRAND_SEGMENT = {
    "lc waikiki": "Ekonomik",
    "fosco": "Ekonomik",
    "southblue": "Ekonomik",
    "ccway": "Ekonomik",
    "zara": "Ulaşılabilir",
    "massimo dutti": "Ulaşılabilir",
    "george hogg": "Ulaşılabilir",
    "beymen club": "Lüks",
    "beymen collection": "Lüks",
    "church's": "Lüks",
}


def segment_for_brand(brand: str) -> str | None:
    return BRAND_SEGMENT.get(brand.casefold().strip())


def catalog_image_url(external_id: str) -> str:
    """Ürünün kendi dosyası varsa onu döndür. Yoksa boş çerçeve için boş adres."""
    if not external_id:
        return ""
    for ext in IMAGE_EXTS:
        if (CATALOG_IMAGES / f"{external_id}{ext}").is_file():
            return f"/catalog-images/{external_id}{ext}"
    return ""


def load_office_catalog() -> dict:
    init_db()
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    live_ids: list[str] = []
    for row in payload["products"]:
        if not row.get("live") or not row.get("url"):
            continue
        expected = segment_for_brand(row["brand"])
        if expected is None or expected != row["segment"]:
            continue
        live_ids.append(row["id"])
        apply_catalog_item(
            {
                "external_id": row["id"],
                "category": row["slot"],
                "sub_category": row["name"],
                "title": row["name"],
                "brand": row["brand"],
                "segment": row["segment"],
                "current_price": float(row["priceTry"]),
                "image_url": catalog_image_url(row["id"]),
                "affiliate_url": row["url"],
                "in_stock": True,
                "description": row["sentence"],
                "source": "office",
                "currency": "TRY",
            },
            now,
        )
    with connect() as conn:
        if live_ids:
            marks = ",".join("?" for _ in live_ids)
            conn.execute(
                f"""
                UPDATE products
                SET in_stock = 0
                WHERE external_id IS NULL OR external_id NOT IN ({marks})
                """,
                live_ids,
            )
            conn.execute(
                f"""
                UPDATE products
                SET in_stock = 1
                WHERE external_id IN ({marks})
                """,
                live_ids,
            )
        conn.commit()
    return {"loaded": len(live_ids)}
