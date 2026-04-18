from __future__ import annotations
import logging
from datetime import datetime, timedelta
import google.generativeai as genai
from database.queries import get_db_summary, get_partner_entries
from config import GEMINI_API_KEY, MAX_HISTORY_TURNS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Sen bir marketing veri asistanısın. Ekip, Telegram üzerinden partner verilerini seninle yönetiyor.

Güncel veritabanı durumu:
{db_summary}

Kurallar:
- Türkçe konuş
- Kısa, net, bilgilendirici ol
- HTML formatını kullan (<b>bold</b>, <i>italic</i>)
- Partner soruşturulduğunda verilere dayanarak yanıt ver
- Veri yoksa açıkça "bu partner veritabanında yok" de
- Tarihleri "3 gün önce", "dün", "bu sabah" gibi doğal ifade et
- Linkleri kısaltma, tam URL yaz
"""

RATE_LIMIT_PER_MINUTE = 10
MODEL_NAME = "gemini-1.5-flash"  # Free tier model


class GeminiAI:
    def __init__(self) -> None:
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(MODEL_NAME)
        # user_id -> ChatSession
        self._sessions: dict[int, genai.ChatSession] = {}
        # user_id -> list of request timestamps (rate limiting)
        self._rate: dict[int, list[datetime]] = {}

    def _is_rate_limited(self, user_id: int) -> bool:
        now = datetime.now()
        cutoff = now - timedelta(minutes=1)
        timestamps = [t for t in self._rate.get(user_id, []) if t > cutoff]
        self._rate[user_id] = timestamps
        if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
            return True
        self._rate[user_id].append(now)
        return False

    def _get_or_create_session(self, user_id: int, system_instruction: str) -> genai.ChatSession:
        """Return existing session or create a new one with fresh context."""
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
            system_instruction = SYSTEM_PROMPT_TEMPLATE.format(db_summary=db_summary)
            session = self._get_or_create_session(user_id, system_instruction)

            response = await session.send_message_async(message)
            return response.text
        except Exception as e:
            logger.error("Gemini chat error for user %s: %s", user_id, e)
            # Reset session on error so next attempt starts fresh
            self.reset_session(user_id)
            return f"❌ AI yanıt verirken hata oluştu: {e}"

    async def summarize_partner(self, tag: str) -> str:
        try:
            partner, entries = await get_partner_entries(tag)
            if not partner:
                return f"❌ <b>#{tag}</b> partneri veritabanında bulunamadı."

            entry_lines = []
            for e in entries:
                entry_lines.append(
                    f"- Tür: {e['entry_type']}, Tarih: {e['created_at']}, "
                    f"Kullanıcı: {e['username'] or 'anonim'}, "
                    f"Link: {e['link'] or '-'}, Açıklama: {e['description'] or '-'}"
                )

            prompt = (
                f"#{tag} partnerinin verilerini analiz et:\n\n"
                + "\n".join(entry_lines)
                + "\n\nBu veriler hakkında Türkçe, HTML formatlı kısa bir analiz yaz. "
                "Toplam kayıt sayısı, veri türleri dağılımı, zaman analizi ve önemli linkleri belirt."
            )

            model = genai.GenerativeModel(MODEL_NAME)
            response = await model.generate_content_async(prompt)
            return response.text
        except Exception as e:
            logger.error("Gemini summarize error for tag %s: %s", tag, e)
            return f"❌ Analiz oluşturulurken hata: {e}"

    async def weekly_report(self) -> str:
        try:
            from database.queries import get_recent
            entries = await get_recent(50)

            entry_lines = []
            for e in entries:
                entry_lines.append(
                    f"- #{e['tag']}, {e['entry_type']}, {e['created_at']}, @{e['username'] or 'anonim'}"
                )

            prompt = (
                "Son 50 kayıt üzerinden haftalık rapor hazırla:\n\n"
                + "\n".join(entry_lines)
                + "\n\nTürkçe, HTML formatlı haftalık özet yaz. "
                "En aktif partnerler, kim en çok ekledi, trend analizi yap."
            )

            model = genai.GenerativeModel(MODEL_NAME)
            response = await model.generate_content_async(prompt)
            return response.text
        except Exception as e:
            logger.error("Gemini weekly report error: %s", e)
            return f"❌ Rapor oluşturulurken hata: {e}"


# Singleton instance
ai = GeminiAI()
