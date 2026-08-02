from __future__ import annotations

import logging
from typing import Any, Optional

from core.services.base import Service, service_tool
from core.services.calendar import CalendarService, GoogleCalendarClient
from core.services.calling import CallingService
from core.services.email import EmailService
from core.services.external import ExternalAPIsService
from core.services.messaging import InboundMessage, MessagingService, OutboundMessage
from core.services.notes import NotesService
from core.services.telegram import TelegramService
from core.tools.base import Tool

logger = logging.getLogger(__name__)


class ServiceManager:
    """Unified registry of all service integrations.

    Constructs every service from the app config, exposes their combined
    tool set for the LLM, and provides health checks.
    """

    def __init__(self, config: Any, services: Optional[list[Service]] = None):
        self.config = config
        self.services: dict[str, Service] = {}
        if services is not None:
            for service in services:
                self.add(service)
        else:
            self._init_from_config()

    def _init_from_config(self) -> None:
        svc = self.config.services

        self.add(NotesService(db_path=svc.notes.db_path))

        self.add(EmailService(
            imap_host=svc.email.imap_host,
            imap_port=svc.email.imap_port,
            smtp_host=svc.email.smtp_host,
            smtp_port=svc.email.smtp_port,
            username=svc.email.username,
            password=svc.email.password,
            from_address=svc.email.from_address,
            use_ssl=svc.email.use_ssl,
        ))

        google = GoogleCalendarClient(
            client_id=svc.calendar.google_client_id,
            client_secret=svc.calendar.google_client_secret,
            refresh_token=svc.calendar.google_refresh_token,
            calendar_id=svc.calendar.google_calendar_id,
        )
        self.add(CalendarService(
            db_path=svc.calendar.db_path,
            provider=svc.calendar.provider,
            google=google if google.is_configured() else None,
            reminders_enabled=svc.calendar.reminders_enabled,
        ))

        self.add(ExternalAPIsService(
            weather_api_key=svc.external.weather_api_key,
            news_api_key=svc.external.news_api_key,
            default_city=svc.external.default_city,
        ))

        self.add(CallingService(
            db_path=svc.calling.db_path,
            provider=svc.calling.provider,
            twilio_account_sid=svc.calling.twilio_account_sid,
            twilio_auth_token=svc.calling.twilio_auth_token,
            twilio_from_number=svc.calling.twilio_from_number,
        ))

        telegram_cfg = getattr(svc, "telegram", None)
        if telegram_cfg and telegram_cfg.enabled:
            self.add(TelegramService(
                api_id=telegram_cfg.api_id,
                api_hash=telegram_cfg.api_hash,
                session_name=telegram_cfg.session_name,
                allowed_users=telegram_cfg.allowed_users,
                owner_chat_id=telegram_cfg.owner_chat_id,
                voice_enabled=telegram_cfg.voice_enabled,
            ))

    def add(self, service: Service) -> None:
        self.services[service.name] = service

    def get(self, name: str) -> Optional[Service]:
        return self.services.get(name)

    def list_names(self) -> list[str]:
        return list(self.services.keys())

    def get_tools(self) -> list[Tool]:
        tools = []
        for service in self.services.values():
            tools.extend(service.get_tools())
        return tools

    async def health_report(self) -> dict[str, dict]:
        report = {}
        for name, service in self.services.items():
            try:
                report[name] = await service.health_check()
            except Exception as e:
                report[name] = {"ok": False, "detail": str(e)}
        return report

    async def close(self) -> None:
        for service in self.services.values():
            try:
                await service.close()
            except Exception as e:
                logger.warning("Error closing service %s: %s", service.name, e)


__all__ = [
    "Service", "service_tool",
    "MessagingService", "InboundMessage", "OutboundMessage",
    "ServiceManager",
    "NotesService", "EmailService", "CalendarService", "GoogleCalendarClient",
    "ExternalAPIsService", "CallingService", "TelegramService",
]
