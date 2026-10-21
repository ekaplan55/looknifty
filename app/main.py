from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.db import catalog_summary, commerce_summary, get_product, init_db, record_click
from app.feed import sync_catalog
from app.match_engine import match_items
from app.models import MatchResponse, VisionAnalysisRequest
from app.office_catalog import CATALOG_IMAGES, load_office_catalog
from app.vision import VisionQuotaError, analyze_image_bytes, load_mock

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

app = FastAPI(title="LookNifty", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CATALOG_IMAGES.mkdir(exist_ok=True)
app.mount("/catalog-images", StaticFiles(directory=CATALOG_IMAGES), name="catalog-images")

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()
    load_office_catalog()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/tanitim")
def tanitim() -> FileResponse:
    return FileResponse(STATIC / "tanitim.html")


@app.get("/gizlilik")
def gizlilik() -> FileResponse:
    return FileResponse(STATIC / "gizlilik.html")


@app.get("/api/v1/health")
def health() -> dict:
    return {
        "ok": True,
        "vision_provider": os.getenv("VISION_PROVIDER", "mock"),
    }


@app.get("/api/v1/catalog/stats")
def catalog_stats() -> dict:
    return catalog_summary()


@app.post("/api/v1/catalog/sync")
def catalog_sync() -> dict:
    totals = sync_catalog()
    return {"ok": True, **totals, "stats": catalog_summary()}


@app.get("/api/v1/commerce/stats")
def commerce_stats() -> dict:
    summary = commerce_summary()
    summary["affiliate_id"] = os.getenv("AFFILIATE_ID", "looknifty_01")
    return summary


@app.get("/go/{product_id}")
def go_to_store(product_id: int) -> RedirectResponse:
    product = get_product(product_id)
    if product is None or not product["in_stock"]:
        raise HTTPException(status_code=404, detail="Ürün stokta yok.")
    target = product["affiliate_url"]
    record_click(
        product_id,
        target,
        datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    return RedirectResponse(target, status_code=302)


@app.post("/api/v1/match", response_model=MatchResponse)
def match(payload: VisionAnalysisRequest) -> MatchResponse:
    t0 = time.perf_counter()
    results = match_items(payload.items)
    return MatchResponse(
        overall_style=payload.overall_style,
        color_palette=payload.color_palette,
        items=payload.items,
        results=results,
        engine_ms=round((time.perf_counter() - t0) * 1000, 2),
        vision_source="request",
    )


@app.post("/api/v1/analyze", response_model=MatchResponse)
async def analyze(file: UploadFile = File(...)) -> MatchResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Yalnızca görsel yükleyin.")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Görsel 8 MB üstünde olamaz.")
    try:
        analysis, source = analyze_image_bytes(raw, file.content_type)
    except VisionQuotaError:
        raise HTTPException(status_code=503, detail="Görüntü kotası doldu. Biraz sonra yeniden dene.")
    except RuntimeError:
        raise HTTPException(status_code=502, detail="Görüntü analizi tamamlanamadı.")
    t0 = time.perf_counter()
    results = match_items(analysis.items)
    return MatchResponse(
        overall_style=analysis.overall_style,
        color_palette=analysis.color_palette,
        items=analysis.items,
        results=results,
        engine_ms=round((time.perf_counter() - t0) * 1000, 2),
        vision_source=source,
    )


@app.get("/api/v1/mock-vision", response_model=VisionAnalysisRequest)
def mock_vision() -> VisionAnalysisRequest:
    return load_mock()
