# Araştırma Notları

## Kütüphane Kararları

### Telegram Kütüphanesi: python-telegram-bot v21
- **Neden:** Async-native (asyncio tabanlı), v21 LTS sürümü, kapsamlı dökümantasyon
- **Alternatif:** aiogram 3.x — daha modern ancak öğrenme eğrisi daha dik
- **Sonuç:** PTB v21, ConversationHandler, InlineKeyboard ve Job Queue desteğiyle bu proje için ideal

### AI: Google Gemini (ücretsiz)
- **Model:** `gemini-1.5-flash` — hızlı, ücretsiz tier, günlük 1500 istek
- **Neden:** Ücretsiz API anahtarı, konuşma geçmişi desteği, Türkçe çok iyi
- **Alternatif:** Claude API (ücretli), OpenAI (ücretli)
- **API Key:** https://aistudio.google.com/app/apikey

### Veritabanı: SQLite + aiosqlite
- **Neden:** Tek dosya, yedekleme kolay (`cp marketing.db backup.db`), ekip ölçeği için yeterli
- **Alternatif:** PostgreSQL — production-grade ama bu proje için fazla karmaşık
- **Sonuç:** SQLite yeterli; ileride büyürse migration kolay

### Polling vs Webhook
- **Seçim:** Long polling
- **Neden:** Public HTTPS URL veya domain gerekmez, VPS'te direkt çalışır, geliştirme ortamında kolay
- **Webhook ne zaman:** 1000+ aktif kullanıcıda webhook daha verimli

### Fotoğraf Stratejisi
- `file_id` Telegram'da sakla (yeniden gönderim için)
- Diske de indir (yedek, offline erişim)
- Klasör yapısı: `photos/{tag}/{file_id}.jpg`

### Konuşma Geçmişi
- In-memory dict — restart'ta sıfırlanır, yeterli
- Gemini ChatSession ile native konuşma geçmişi yönetimi
- Max 10 tur geçmiş (config ile ayarlanabilir)

## Benzer Projeler

- `vicgalle/personalCRMbot` — basit SQLite CRM, hashtag yok
- TeleMe.io — grup analytics, hashtag tabanlı değil
- Umnico/Planfix — enterprise CRM, Telegram entegrasyonu var ama overkill

## Özellik Farkları (Rakiplerden Fark)
- Hashtag tabanlı veri organizasyonu (benzersiz)
- Link duplicate detection
- Fotoğraf otomatik partner atama
- Gemini AI ile Türkçe doğal dil sorgu
