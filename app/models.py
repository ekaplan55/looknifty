from typing import Optional

from pydantic import BaseModel, Field


class OutfitItem(BaseModel):
    category: str
    sub_category: str
    description: str
    color: str
    style_tags: list[str] = Field(default_factory=list)
    hotspot_x: Optional[float] = None
    hotspot_y: Optional[float] = None


class VisionAnalysisRequest(BaseModel):
    source_image: str = "upload.jpg"
    overall_style: str = "Smart Casual"
    color_palette: list[str] = Field(default_factory=list)
    items: list[OutfitItem]


class ProductMatch(BaseModel):
    id: int
    title: str
    brand: str
    category: str
    sub_category: str
    segment: str
    current_price: float
    old_price: Optional[float] = None
    image_url: str
    affiliate_url: str
    in_stock: bool
    vector_similarity_score: float
    price_drop_alert: bool = False
    match_label: str = ""


class MatchGroup(BaseModel):
    target_piece: str
    category: str
    query_label: str = ""
    query_sentence: str = ""
    matched_alternatives: list[ProductMatch]


class MatchResponse(BaseModel):
    overall_style: str
    color_palette: list[str]
    items: list[OutfitItem] = Field(default_factory=list)
    results: list[MatchGroup]
    engine_ms: float
    vision_source: str = "request"
