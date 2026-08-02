from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from core.services.telegram import TelegramService
from core.services.telegram_confirmation import ConfirmationManager
from core.services.telegram_events import TelegramEventHandler
from core.services.telegram_reminders import ReminderPoller
from core.services.telegram_voice import TelegramVoiceProcessor
from core.session import JarvisSession

logger = logging.getLogger(__name__)


def _sarvam_api_key(config: Any) -> str:
    key = getattr(getattr(config, "sarvam", None), "api_key", "") or ""
    return key or os.getenv("SARVAM_API_KEY", "")


def build_voice_processor(session: JarvisSession) -> Optional[TelegramVoiceProcessor]:
    cfg = getattr(session.config, "sarvam", None)
    api_key = _sarvam_api_key(session.config)
    if not cfg or not api_key:
        return None
    from voice.sarvam_stt import SarvamSTT
    from voice.sarvam_tts import SarvamTTS

    return TelegramVoiceProcessor(
        session=session,
        stt=SarvamSTT(
            api_key=api_key,
            model=cfg.stt_model,
            language_code=cfg.stt_language_code,
            with_translation=cfg.stt_with_translation,
        ),
        tts=SarvamTTS(
            api_key=api_key,
            model=cfg.tts_model,
            language_code=cfg.tts_language_code,
            voice=session.get_voice_for_active(),
            speed=cfg.tts_pace,
        ),
    )


async def run_telegram(config_path: str | os.PathLike | None = None) -> None:
    """Boot the standard JARVIS runtime and run the Telegram service."""
    from dotenv import load_dotenv
    load_dotenv()

    session = JarvisSession(config_path=config_path)
    telegram: Optional[TelegramService] = None
    if session.service_manager is not None:
        telegram = session.service_manager.get("telegram")
    if telegram is None:
        raise RuntimeError(
            "Telegram service is not enabled. Set services.telegram.enabled=true "
            "in config.yaml (and TELEGRAM_API_ID / TELEGRAM_API_HASH)."
        )

    confirmation = ConfirmationManager(telegram)
    voice_processor = build_voice_processor(session)
    handler = TelegramEventHandler(
        service=telegram,
        session=session,
        owner_chat_id=telegram.owner_chat_id,
        voice_processor=voice_processor,
        confirmation_manager=confirmation,
    )
    telegram.attach_event_handler(handler)

    poller = ReminderPoller(
        calendar_service=session.service_manager.get("calendar")
        if session.service_manager is not None
        else None,
        service=telegram,
        owner_chat_id=telegram.owner_chat_id,
        allowed_users=sorted(telegram.allowed_users),
    )

    try:
        await telegram.start()
        if poller.enabled:
            poller.start()
            logger.info("Reminder poller started (interval=%ss)", poller.interval)
        logger.info("JARVIS Telegram running. Press Ctrl+C to stop.")
        await asyncio.Future()  # run forever
    finally:
        await poller.stop()
        confirmation.cancel_all()
        await telegram.stop()
        await session.cleanup()
