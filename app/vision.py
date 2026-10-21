from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from app.models import OutfitItem, VisionAnalysisRequest

MOCK_PATH = Path(__file__).resolve().parent.parent / "data" / "mock_vision.json"

SYSTEM_PROMPT = """Sen LookNifty görsel analiz motorusun.
Kombin fotoğrafındaki kıyafet parçalarını JSON olarak çıkar.
Şema:
{
  "source_image": "upload.jpg",
  "overall_style": "string",
  "color_palette": ["string"],
  "items": [
    {
      "category": "Üst Giyim | Alt Giyim | Ayakkabı | Aksesuar",
      "sub_category": "string",
      "description": "string",
      "color": "string",
      "style_tags": ["string"],
      "hotspot_x": 0-100,
      "hotspot_y": 0-100
    }
  ]
}
Sadece JSON döndür."""


def load_mock() -> VisionAnalysisRequest:
    payload = json.loads(MOCK_PATH.read_text(encoding="utf-8"))
    return VisionAnalysisRequest.model_validate(payload)


class VisionQuotaError(RuntimeError):
    """Görüntü sağlayıcısının kotası doldu."""


def analyze_image_bytes(image_bytes: bytes, mime: str = "image/jpeg") -> tuple[VisionAnalysisRequest, str]:
    provider = (os.getenv("VISION_PROVIDER") or "mock").strip().lower()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return _openai(image_bytes, mime), "openai"
    if provider == "gemini" and os.getenv("GEMINI_API_KEY"):
        try:
            return _gemini(image_bytes, mime), "gemini"
        except VisionQuotaError:
            if os.getenv("OPENAI_API_KEY"):
                return _openai(image_bytes, mime), "openai"
            raise
    return load_mock(), "mock"


def _parse_json_object(text: str) -> VisionAnalysisRequest:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return VisionAnalysisRequest.model_validate(json.loads(cleaned))


def _openai(image_bytes: bytes, mime: str) -> VisionAnalysisRequest:
    import base64

    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    with httpx.Client(timeout=60) as client:
        response = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"},
            json={
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Bu kombin fotoğrafını analiz et."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                        ],
                    },
                ],
            },
        )
        if response.status_code == 429:
            raise VisionQuotaError("OpenAI kotası doldu.")
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI {response.status_code}")
        content = response.json()["choices"][0]["message"]["content"]
    return _parse_json_object(content)


def _gemini_models() -> list[str]:
    preferred = os.getenv("GEMINI_VISION_MODEL", "gemini-3.5-flash-lite")
    fallbacks = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
        "gemini-flash-latest",
    ]
    ordered = [preferred, *[name for name in fallbacks if name != preferred]]
    return ordered


def _gemini(image_bytes: bytes, mime: str) -> VisionAnalysisRequest:
    import base64

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY tanımlı değil.")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT + "\nBu kombin fotoğrafını analiz et."},
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ]
            }
        ],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    last_status = None
    quota_hit = False
    with httpx.Client(timeout=60) as client:
        for model in _gemini_models():
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key},
                json=payload,
            )
            if response.status_code in (404, 429, 503):
                last_status = response.status_code
                quota_hit = quota_hit or response.status_code == 429
                continue
            if response.status_code >= 400:
                raise RuntimeError(f"Gemini {response.status_code}")
            content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            return _parse_json_object(content)
    if quota_hit:
        raise VisionQuotaError("Gemini kotası doldu.")
    raise RuntimeError(f"Gemini model bulunamadı (son durum {last_status}).")


def default_items() -> list[OutfitItem]:
    return load_mock().items
