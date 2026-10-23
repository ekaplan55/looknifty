# LookNifty

Kombin görselinden kıyafet parçası çıkarıp Lüks / Ulaşılabilir / Ekonomik alternatifleri eşleştiren Fashion-Tech API ve arayüz.

## Çalıştırma

```powershell
cd C:\Users\pc\looknifty-app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Aç: http://127.0.0.1:8000

## Vision

`.env` içinde:

- `VISION_PROVIDER=mock` — `data/mock_vision.json`
- `VISION_PROVIDER=openai` + `OPENAI_API_KEY`
- `VISION_PROVIDER=gemini` + `GEMINI_API_KEY`

## Katalog

`data/feeds` altındaki JSON ve XML dosyaları açılışta içeri alınır. Fiyat değişince `price_history` yazılır. Segment feed'de yoksa fiyat bandı kullanılır: 1000 TL altı Ekonomik, 8000 TL altı Ulaşılabilir, üzeri Lüks.

Canlı kaynak için `.env` içine yalnızca https bir resmi feed koy:

```
FEED_URL=https://example-affiliate.example/feed.xml
```

Elle çalıştırma:

```powershell
python -m app.feed
```

`POST /api/v1/catalog/sync` yerel feed'leri ve `FEED_URL` değerini yeniden işler.

## Ticaret

Satın Al linki önce `/go/{ürün}` adresine gider. Tıklama `clicks` tablosuna yazılır, sonra `affiliate_url` adresine yönlendirilir. Kimlik `.env` içindeki `AFFILIATE_ID` değeridir. Gerçek ağ linki feed'deki `affiliate_url` alanıdır.

## API

- `POST /api/v1/match` — vision JSON → eşleşmeler
- `POST /api/v1/analyze` — görsel yükle → vision + eşleşme
- `GET /api/v1/health`
- `GET /api/v1/catalog/stats`
- `POST /api/v1/catalog/sync`
