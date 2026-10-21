from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.db import fetch_products
from app.models import MatchGroup, OutfitItem, ProductMatch
from app.office_catalog import catalog_image_url

SLOTS = ("Üst", "Alt", "Ayakkabı")
SEGMENTS = ("Ekonomik", "Ulaşılabilir", "Lüks")
MATCH_PERCENT = 60

# Skor cümlesinde marka yok. Karşılaştırılan metin renk, tür ve malzemedir.
SCORE_TEXT = {
    "taba oxford": "taba deri oxford ayakkabı",
    "beyaz sneaker": "beyaz deri sneaker",
}
TRAIT_TERMS = (
    ("ayakkabı", "ayakkabı"),
    ("ayakkabi", "ayakkabı"),
    ("tişört", "tişört"),
    ("tisort", "tişört"),
    ("gömlek", "gömlek"),
    ("gomlek", "gömlek"),
    ("pantolon", "pantolon"),
    ("sneaker", "sneaker"),
    ("gabardin", "gabardin"),
    ("oxford", "oxford"),
    ("chino", "chino"),
    ("klasik", "klasik"),
    ("derby", "derby"),
    ("loafer", "loafer"),
    ("keten", "keten"),
    ("pamuk", "pamuk"),
    ("süet", "süet"),
    ("suet", "süet"),
    ("deri", "deri"),
    ("yün", "yün"),
    ("yun", "yün"),
    ("kahverengi", "kahverengi"),
    ("lacivert", "lacivert"),
    ("beyaz", "beyaz"),
    ("ekru", "ekru"),
    ("taba", "taba"),
    ("bej", "bej"),
    ("siyah", "siyah"),
    ("haki", "haki"),
    ("mavi", "mavi"),
)

SLOT_ALIASES = {
    "ust": "Üst",
    "üst": "Üst",
    "ust giyim": "Üst",
    "üst giyim": "Üst",
    "alt": "Alt",
    "alt giyim": "Alt",
    "ayakkabi": "Ayakkabı",
    "ayakkabı": "Ayakkabı",
}


def normalize_slot(value: str) -> str:
    key = value.casefold().strip()
    return SLOT_ALIASES.get(key, value.strip())


def _sentence(item: OutfitItem) -> str:
    if item.description.strip():
        return item.description.strip()
    return " ".join(
        part
        for part in [item.sub_category, item.color, item.description, " ".join(item.style_tags)]
        if part
    )


def _tr(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").casefold()


_SUFFIXES = {
    "i", "ı", "u", "ü", "si", "sı", "su", "sü", "yi", "yı", "yu", "yü",
    "in", "ın", "un", "ün", "nin", "nın", "nun", "nün",
    "den", "dan", "ten", "tan", "de", "da", "te", "ta",
    "li", "lı", "lu", "lü",
}


def _same_term(token: str, stem: str) -> bool:
    if token == stem:
        return True
    return token.startswith(stem) and token[len(stem):] in _SUFFIXES


def _traits(text: str) -> str:
    found: list[str] = []
    for token in re.findall(r"[a-z0-9çğıöşü]+", _tr(text)):
        for stem, canon in TRAIT_TERMS:
            if _same_term(token, stem):
                if canon not in found:
                    found.append(canon)
                break
    return " ".join(found)


def _score_text(product: dict) -> str:
    prescribed = SCORE_TEXT.get(_tr(product["title"]))
    if prescribed:
        return prescribed
    return _traits(product.get("description") or "")


def _luxury_missing(query_text: str, luxury_texts: list[str]) -> bool:
    words = set(query_text.split())
    if "keten" in words and "gömlek" in words:
        has_linen = any({"keten", "gömlek"} <= set(text.split()) for text in luxury_texts)
        if not has_linen:
            return True
    if "sneaker" in words:
        has_sneaker = any("sneaker" in text.split() for text in luxury_texts)
        if not has_sneaker:
            return True
    return False


def _badge(value: float, segment: str, block_luxury: bool) -> str:
    if segment == "Lüks" and block_luxury:
        return "En yakın"
    if round(value * 100) >= MATCH_PERCENT:
        return "Eşleşme"
    return "En yakın"


def _winner(product: dict, value: float, block_luxury: bool) -> ProductMatch:
    return ProductMatch(
        id=product["id"],
        title=product["title"],
        brand=product["brand"],
        category=product["category"],
        sub_category=product["sub_category"],
        segment=product["segment"],
        current_price=product["current_price"],
        old_price=None,
        image_url=catalog_image_url(product.get("external_id") or ""),
        affiliate_url=product["affiliate_url"],
        in_stock=bool(product["in_stock"]),
        vector_similarity_score=round(value, 4),
        price_drop_alert=False,
        match_label=_badge(value, product["segment"], block_luxury),
    )


def _slot_scores(item: OutfitItem, rows: list[dict]) -> list[tuple[dict, float]]:
    query = _traits(_sentence(item))
    usable = [(row, _score_text(row)) for row in rows]
    usable = [(row, text) for row, text in usable if text]
    if not query or not usable:
        return []
    vectorizer = TfidfVectorizer()
    matrix = vectorizer.fit_transform([text for _, text in usable])
    scores = cosine_similarity(vectorizer.transform([query]), matrix)[0]
    return [(row, float(score)) for (row, _), score in zip(usable, scores) if float(score) > 0]


def match_items(items: list[OutfitItem], top_per_segment: int = 8) -> list[MatchGroup]:
    catalog = [row for row in fetch_products() if row.get("description")]
    by_slot: dict[str, OutfitItem] = {}
    for item in items:
        slot = normalize_slot(item.category)
        if slot in SLOTS and slot not in by_slot:
            by_slot[slot] = item

    groups: list[MatchGroup] = []
    for slot in SLOTS:
        item = by_slot.get(slot)
        ranked: list[ProductMatch] = []
        if item is not None and catalog:
            rows = [row for row in catalog if normalize_slot(row["category"]) == slot]
            paired = _slot_scores(item, rows)
            luxury_texts = [_score_text(row) for row in rows if row["segment"] == "Lüks"]
            block_luxury = _luxury_missing(_traits(_sentence(item)), luxury_texts)
            buckets: dict[str, list[tuple[dict, float]]] = {segment: [] for segment in SEGMENTS}
            for product, value in paired:
                if product["segment"] in buckets:
                    buckets[product["segment"]].append((product, value))
            for segment in SEGMENTS:
                chosen = sorted(buckets[segment], key=lambda pair: pair[1], reverse=True)[:top_per_segment]
                ranked.extend(_winner(product, value, block_luxury) for product, value in chosen)
        groups.append(
            MatchGroup(
                target_piece=slot,
                category=slot,
                query_label=item.sub_category if item else "",
                query_sentence=_sentence(item) if item else "",
                matched_alternatives=ranked,
            )
        )
    return groups
