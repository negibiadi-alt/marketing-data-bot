from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

import google.generativeai as genai

from database.queries import get_db_summary, get_partner_entries
from config import GEMINI_API_KEY, MAX_HISTORY_TURNS

logger = logging.getLogger(__name__)

RATE_LIMIT_PER_MINUTE = 10
MODEL_NAME = "gemini-1.5-flash"

# ─────────────────────────────────────────────
# Intent extraction result
# ─────────────────────────────────────────────

@dataclass
class Intent:
    type: Literal["SAVE", "QUERY", "CHAT"]
    partner: str | None = None          # lowercase, no #
    links: list[str] = field(default_factory=list)
    description: str | None = None


INTENT_PROMPT = """Aşağıdaki Telegram mesajını analiz et ve sadece JSON döndür.

Mesaj: {message}

JSON formatı:
{{
  "intent": "SAVE" veya "QUERY" veya "CHAT",
  "partner": "partner_adı veya null",
  "links": ["https://..."],
  "description": "açıklama veya null"
}}

Kurallar:
- SAVE: Kullanıcı bir bilgi/not/link kaydetmek istiyor. İşbirlikçi hakkında bilgi veriyor, çalışma linki atıyor, panel ss vs.
- QUERY: Daha önce kaydedilen bir şeyi soruyor. "kimdi", "ne yapıyordu", "hangi sitede", "ne zaman", "hatırlıyor musun" gibi ifadeler.
- CHAT: Ne kaydetme ne sorgulama.
- partner: Kişi/firma/nick adı — varsa çıkar. Küçük harf, boşluk yerine "_". Örnek: "bigbangers", "ahmet_usta". Yoksa null.
- links: Mesajdaki tüm URL'ler. Boşsa [].
- description: Link ve partner adı dışındaki bilgi. Yoksa null.

Sadece JSON döndür, başka hiçbir şey yazma."""

# ─────────────────────────────────────────────
# System prompt for recall/chat
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Sen bir kişisel iş hafızasısın. Kullanıcı işbirlikçileri ve iş partnerlerini seninle takip ediyor.

Veritabanı durumu (şu an):
{db_summary}

Kurallar:
- Türkçe konuş, samimi ve kısa ol
- HTML formatı: <b>bold</b>, <i>italic</i>
- Birisi hakkında soru gelince veritabanındaki TÜM bilgileri göster: tarih, site, açıklama, kaç kayıt
- Tarihleri "18 Nisan 2026", "3 gün önce", "dün" gibi doğal ifade et
- Veri yoksa "kayıtlı bilgi yok" de, uydurma
- Linkler varsa tam URL yaz"""


class GeminiAI:
    def __init__(self) -> None:
        genai.configure(api_key=GEMINI_API_KEY)
        self._extract_model = genai.GenerativeModel(MODEL_NAME)
        # user_id -> ChatSession (for recall/chat)
        self._sessions: dict[int, genai.ChatSession] = {}
        # rate limiting: user_id -> list of timestamps
        self._rate: dict[int, list[datetime]] = {}

    # ── Rate limiting ──────────────────────────────────────

    def _is_rate_limited(self, user_id: int) -> bool:
        now = datetime.now()
        cutoff = now - timedelta(minutes=1)
        timestamps = [t for t in self._rate.get(user_id, []) if t > cutoff]
        self._rate[user_id] = timestamps
        if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
            return True
        self._rate[user_id].append(now)
        return False

    # ── Intent extraction ──────────────────────────────────

    async def classify(self, text: str) -> Intent:
        """Classify message intent and extract structured data."""
        try:
            prompt = INTENT_PROMPT.format(message=text)
            response = await self._extract_model.generate_content_async(prompt)
            raw = response.text.strip()

            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            data = json.loads(raw)
            return Intent(
                type=data.get("intent", "CHAT"),
                partner=data.get("partner") or None,
                links=data.get("links") or [],
                description=data.get("description") or None,
            )
        except Exception as e:
            logger.warning("Intent classification failed: %s — fallback to CHAT", e)
            return Intent(type="CHAT")

    # ── Chat / Recall ──────────────────────────────────────

    def _get_session(self, user_id: int, system_instruction: str) -> genai.ChatSession:
        if user_id not in self._sessions:
            model = genai.GenerativeModel(
                MODEL_NAME,
                system_instruction=system_instruction,
            )
            self._sessions[user_id] = model.start_chat(history=[])
        return self._sessions[user_id]

    def reset_session(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)

    async def chat(self, user_id: int, username: str | None, message: str) -> str:
        if self._is_rate_limited(user_id):
            return "⏳ Çok hızlı sorgu gönderiyorsunuz. Lütfen bir dakika bekleyin."
        try:
            db_summary = await get_db_summary()
            system = SYSTEM_PROMPT.format(db_summary=db_summary)
            session = self._get_session(user_id, system)
            response = await session.send_message_async(message)
            return response.text
        except Exception as e:
            logger.error("Gemini chat error for user %s: %s", user_id, e)
            self.reset_session(user_id)
            return f"❌ AI yanıt verirken hata oluştu: {e}"

    # ── Partner AI summary ─────────────────────────────────

    async def summarize_partner(self, tag: str) -> str:
        try:
            partner, entries = await get_partner_entries(tag)
            if not partner:
                return f"❌ <b>#{tag}</b> veritabanında bulunamadı."

            lines = []
            for e in entries:
                lines.append(
                    f"- [{e['created_at']}] tür:{e['entry_type']} "
                    f"kim:@{e['username'] or 'anonim'} "
                    f"link:{e['link'] or '-'} açıklama:{e['description'] or '-'}"
                )

            prompt = (
                f"#{tag} iş partnerinin tüm kayıtlarını analiz et:\n\n"
                + "\n".join(lines)
                + "\n\nTürkçe, HTML formatlı özet yaz. "
                "Ne zaman tanındı, hangi sitelerde çalışıyor, ne tür veriler var, önemli notlar."
            )
            response = await self._extract_model.generate_content_async(prompt)
            return response.text
        except Exception as e:
            logger.error("Gemini summarize error for %s: %s", tag, e)
            return f"❌ Analiz hatası: {e}"

    # ── Weekly report ──────────────────────────────────────

    async def weekly_report(self) -> str:
        try:
            from database.queries import get_recent
            entries = await get_recent(50)
            lines = [
                f"- #{e['tag']} {e['entry_type']} {e['created_at']} @{e['username'] or 'anonim'}"
                for e in entries
            ]
            prompt = (
                "Son 50 kayıt üzerinden haftalık rapor hazırla:\n\n"
                + "\n".join(lines)
                + "\n\nTürkçe, HTML formatlı. En aktif partnerler, kim ne ekledi, trend."
            )
            response = await self._extract_model.generate_content_async(prompt)
            return response.text
        except Exception as e:
            logger.error("Gemini weekly report error: %s", e)
            return f"❌ Rapor hatası: {e}"


# Singleton
ai = GeminiAI()
