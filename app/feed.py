"""Resmi affiliate XML/JSON ürün feed içe aktarma.

Kazıma yok. Kaynaklar: data/feeds altındaki dosyalar ve isteğe bağlı FEED_URL.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.db import apply_catalog_item, init_db, record_catalog_run
from app.seed import seed

ROOT = Path(__file__).resolve().parent.parent
FEED_DIR = ROOT / "data" / "feeds"
G_NS = {"g": "http://base.google.com/ns/1.0"}
SEGMENTS = ("Lüks", "Ulaşılabilir", "Ekonomik")


def infer_segment(price: float, explicit: str | None) -> str:
    if explicit in SEGMENTS:
        return explicit
    if price < 1000:
        return "Ekonomik"
    if price < 8000:
        return "Ulaşılabilir"
    return "Lüks"


def parse_price(value: str | float | int) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^\d,.\-]", "", str(value).strip())
    if not text:
        raise ValueError("fiyat yok")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


def with_affiliate(url: str) -> str:
    aff = os.getenv("AFFILIATE_ID", "looknifty_01").strip() or "looknifty_01"
    if "aff_id=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}aff_id={aff}"


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _child(parent: ET.Element, name: str) -> str:
    found = parent.find(name)
    if found is not None and found.text:
        return found.text.strip()
    found = parent.find(f"g:{name}", G_NS)
    if found is not None and found.text:
        return found.text.strip()
    return ""


def _split_type(product_type: str, category: str, sub_category: str) -> tuple[str, str]:
    if category and sub_category:
        return category, sub_category
    parts = [part.strip() for part in re.split(r">|/", product_type) if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if category and parts:
        return category, parts[-1]
    if parts:
        return parts[0], parts[-1]
    return category, sub_category


def _item_from_fields(fields: dict, source: str) -> dict | None:
    external_id = str(fields.get("external_id") or fields.get("id") or "").strip()
    title = str(fields.get("title") or "").strip()
    if not external_id or not title:
        return None
    try:
        price = parse_price(fields.get("price") or fields.get("current_price"))
    except (TypeError, ValueError):
        return None
    category, sub_category = _split_type(
        str(fields.get("product_type") or ""),
        str(fields.get("category") or "").strip(),
        str(fields.get("sub_category") or "").strip(),
    )
    if not category or not sub_category:
        return None
    availability = str(fields.get("availability") or fields.get("in_stock") or "in stock").strip().lower()
    in_stock = availability not in {"0", "false", "out of stock", "outofstock", "yok"}
    image_url = str(fields.get("image_url") or fields.get("image_link") or "").strip()
    affiliate_url = str(fields.get("affiliate_url") or fields.get("link") or fields.get("url") or "").strip()
    if not image_url or not affiliate_url:
        return None
    brand = str(fields.get("brand") or "Marka").strip()
    description = str(fields.get("description") or title).strip()
    segment = infer_segment(price, str(fields.get("segment") or "").strip() or None)
    return {
        "external_id": external_id,
        "category": category,
        "sub_category": sub_category,
        "title": title,
        "brand": brand,
        "segment": segment,
        "current_price": price,
        "image_url": image_url,
        "affiliate_url": with_affiliate(affiliate_url),
        "in_stock": in_stock,
        "description": description,
        "source": source,
        "currency": str(fields.get("currency") or "TRY").strip() or "TRY",
    }


def parse_json_feed(raw: str, source: str) -> list[dict]:
    payload = json.loads(raw)
    rows = payload["products"] if isinstance(payload, dict) else payload
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = _item_from_fields(row, source)
        if item:
            items.append(item)
    return items


def parse_xml_feed(raw: str, source: str) -> list[dict]:
    root = ET.fromstring(raw)
    nodes = list(root.iter("product")) + list(root.iter("item"))
    items = []
    for node in nodes:
        fields = {
            "external_id": _child(node, "external_id") or _child(node, "id"),
            "title": _child(node, "title"),
            "brand": _child(node, "brand"),
            "category": _child(node, "category"),
            "sub_category": _child(node, "sub_category"),
            "product_type": _child(node, "product_type"),
            "price": _child(node, "price") or _child(node, "current_price"),
            "image_url": _child(node, "image_url") or _child(node, "image_link"),
            "affiliate_url": _child(node, "affiliate_url") or _child(node, "link"),
            "description": _child(node, "description"),
            "availability": _child(node, "availability") or _child(node, "in_stock"),
            "segment": _child(node, "segment"),
            "currency": _child(node, "currency"),
        }
        item = _item_from_fields(fields, source)
        if item:
            items.append(item)
    return items


def parse_feed(raw: str, source: str) -> list[dict]:
    stripped = raw.lstrip()
    if stripped.startswith("<"):
        return parse_xml_feed(raw, source)
    return parse_json_feed(raw, source)


def import_items(items: list[dict], source: str, skipped: int = 0) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": skipped}
    for item in items:
        result = apply_catalog_item(item, now)
        counts[result] += 1
    summary = {"source": source, "finished_at": now, **counts}
    record_catalog_run(summary)
    return summary


def import_text(raw: str, source: str) -> dict:
    init_db()
    try:
        items = parse_feed(raw, source)
    except (json.JSONDecodeError, ET.ParseError) as exc:
        raise ValueError(f"Feed okunamadı: {exc}") from exc
    return import_items(items, source)


def import_path(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    return import_text(raw, path.name)


def import_local_feeds() -> list[dict]:
    FEED_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(
        [
            path
            for path in [*FEED_DIR.glob("*.json"), *FEED_DIR.glob("*.xml")]
            if not path.name.startswith("sample_")
        ],
        key=lambda path: path.name,
    )
    return [import_path(path) for path in paths]


def import_remote_feed(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("FEED_URL yalnızca https olabilir.")
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        final = urlparse(str(response.url))
        if final.scheme != "https":
            raise ValueError("Feed yönlendirmesi https dışında kaldı.")
        if len(response.content) > 20 * 1024 * 1024:
            raise ValueError("Feed 20 MB sınırını aşıyor.")
    return import_text(response.text, parsed.netloc)


def sync_catalog() -> dict:
    seed()
    runs = import_local_feeds()
    remote = (os.getenv("FEED_URL") or "").strip()
    remote_error = None
    if remote:
        try:
            runs.append(import_remote_feed(remote))
        except Exception as exc:
            remote_error = str(exc)
    totals = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0, "feeds": len(runs)}
    for run in runs:
        for key in ("inserted", "updated", "unchanged", "skipped"):
            totals[key] += run[key]
    if remote_error:
        totals["remote_error"] = remote_error
    return totals


if __name__ == "__main__":
    result = sync_catalog()
    print(
        "feeds={feeds} inserted={inserted} updated={updated} unchanged={unchanged} skipped={skipped}".format(
            **result
        )
    )
    if result.get("remote_error"):
        print("remote_error=" + result["remote_error"])
