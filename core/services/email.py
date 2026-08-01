from __future__ import annotations

import asyncio
import imaplib
import logging
import os
import smtplib
from email import encoders
from email.header import decode_header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, parseaddr
from pathlib import Path
from typing import Any, Optional

from core.services.base import Service, service_tool
from core.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


def _decode_header(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    result = ""
    for chunk, encoding in parts:
        if isinstance(chunk, bytes):
            try:
                result += chunk.decode(encoding or "utf-8", errors="replace")
            except (LookupError, UnicodeDecodeError):
                result += chunk.decode("utf-8", errors="replace")
        else:
            result += chunk
    return result


class EmailService(Service):
    """Email integration via IMAP (read/search) and SMTP (send)."""

    name = "email"
    description = "Send and read email via IMAP/SMTP."

    def __init__(
        self,
        imap_host: str = "",
        imap_port: int = 993,
        smtp_host: str = "",
        smtp_port: int = 587,
        username: str = "",
        password: str = "",
        from_address: str = "",
        use_ssl: bool = True,
    ):
        self.imap_host = imap_host or os.getenv("EMAIL_IMAP_HOST", "")
        self.imap_port = imap_port
        self.smtp_host = smtp_host or os.getenv("EMAIL_SMTP_HOST", "")
        self.smtp_port = smtp_port
        self.username = username or os.getenv("EMAIL_USERNAME", "")
        self.password = password or os.getenv("EMAIL_PASSWORD", "")
        self.from_address = from_address or os.getenv("EMAIL_FROM", "") or self.username
        self.use_ssl = use_ssl

    def is_configured(self) -> bool:
        return bool(self.imap_host and self.smtp_host and self.username and self.password)

    def _imap(self) -> imaplib.IMAP4:
        if self.use_ssl or self.imap_port == 993:
            conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        else:
            conn = imaplib.IMAP4(self.imap_host, self.imap_port)
        conn.login(self.username, self.password)
        return conn

    def _smtp(self) -> smtplib.SMTP:
        if self.use_ssl or self.smtp_port == 465:
            conn = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
        else:
            conn = smtplib.SMTP(self.smtp_host, self.smtp_port)
            conn.starttls()
        conn.login(self.username, self.password)
        return conn

    def _wrap_headers(self, message: MIMEMultipart, to: str, subject: str) -> MIMEMultipart:
        message["From"] = self.from_address
        message["To"] = to
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=True)
        return message

    def _build_message(self, to: str, subject: str, body: str, attachments: Optional[list[str]] = None) -> MIMEMultipart:
        msg = MIMEMultipart()
        msg["From"] = self.from_address
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg.attach(MIMEText(body, "plain", "utf-8"))
        for path in attachments or []:
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"Attachment not found: {path}")
            part = MIMEBase("application", "octet-stream")
            part.set_payload(p.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=p.name)
            msg.attach(part)
        return msg

    async def send_email(self, to: str, subject: str, body: str, attachments: Optional[list[str]] = None) -> ToolResult:
        if not self.is_configured():
            return ToolResult(success=False, error="Email not configured. Set EMAIL_IMAP_HOST, EMAIL_SMTP_HOST, EMAIL_USERNAME, EMAIL_PASSWORD.")
        if not to or not subject:
            return ToolResult(success=False, error="Both 'to' and 'subject' are required.")
        try:
            msg = self._build_message(to, subject, body, attachments)
            await asyncio.to_thread(self._send, msg)
            return ToolResult(success=True, output=f"Email sent to {to} with subject '{subject}'")
        except Exception as e:
            logger.exception("send_email failed")
            return ToolResult(success=False, error=f"Failed to send email: {e}")

    def _send(self, msg: MIMEMultipart) -> None:
        with self._smtp() as conn:
            conn.send_message(msg)

    async def read_unread(self, count: int = 5, mailbox: str = "INBOX") -> list[dict]:
        if not self.is_configured():
            return [{"error": "Email not configured. Set EMAIL_IMAP_HOST, EMAIL_USERNAME, EMAIL_PASSWORD."}]
        try:
            return await asyncio.to_thread(self._read_unread, count, mailbox)
        except Exception as e:
            logger.exception("read_unread failed")
            return [{"error": str(e)}]

    def _read_unread(self, count: int, mailbox: str) -> list[dict]:
        conn = self._imap()
        try:
            conn.select(mailbox, readonly=True)
            _, data = conn.search(None, "UNSEEN")
            ids = data[0].split()
            results = []
            for msg_id in ids[-count:]:
                _, msg_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER] BODY.PEEK[TEXT])")
                header, body = self._parse_fetch(msg_data)
                results.append({
                    "id": msg_id.decode(),
                    "from": self._extract_from(header),
                    "subject": _decode_header(header.get("Subject", "")),
                    "date": _decode_header(header.get("Date", "")),
                    "body": _decode_header(body)[:500],
                })
            return results
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    async def search_emails(self, query: str, count: int = 10, mailbox: str = "INBOX") -> list[dict]:
        if not self.is_configured():
            return [{"error": "Email not configured. Set EMAIL_IMAP_HOST, EMAIL_USERNAME, EMAIL_PASSWORD."}]
        try:
            return await asyncio.to_thread(self._search_emails, query, count, mailbox)
        except Exception as e:
            logger.exception("search_emails failed")
            return [{"error": str(e)}]

    def _search_emails(self, query: str, count: int, mailbox: str) -> list[dict]:
        conn = self._imap()
        try:
            conn.select(mailbox, readonly=True)
            typ, data = conn.search(None, "TEXT", f'"{query}"')
            if typ != "OK":
                return [{"error": f"Search failed: {typ}"}]
            ids = data[0].split()
            results = []
            for msg_id in ids[-count:]:
                _, msg_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER] BODY.PEEK[TEXT])")
                header, body = self._parse_fetch(msg_data)
                results.append({
                    "id": msg_id.decode(),
                    "from": self._extract_from(header),
                    "subject": _decode_header(header.get("Subject", "")),
                    "date": _decode_header(header.get("Date", "")),
                    "body": _decode_header(body)[:500],
                })
            return results
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    @staticmethod
    def _parse_fetch(msg_data: list) -> tuple[Any, str]:
        header_parts: list[bytes] = []
        body_parts: list[bytes] = []
        for part in msg_data:
            if isinstance(part, tuple):
                raw = part[1]
                if "BODY[TEXT]" in (part[0].decode(errors="replace")):
                    body_parts.append(raw)
                else:
                    header_parts.append(raw)
        import email as email_mod
        from email import parser
        header_msg = parser.BytesParser().parsebytes(b"".join(header_parts)) if header_parts else email_mod.message.Message()
        body = ""
        if body_parts:
            body = b"".join(body_parts).decode("utf-8", errors="replace")
        return header_msg, body

    @staticmethod
    def _extract_from(header: Any) -> str:
        raw = header.get("From", "")
        name, addr = parseaddr(raw)
        return f"{_decode_header(name)} <{addr}>" if name else addr or raw

    @staticmethod
    def format_email_list(items: list[dict]) -> str:
        if not items:
            return "No emails found."
        if len(items) == 1 and items[0].get("error"):
            return items[0]["error"]
        lines = []
        for m in items:
            lines.append(f"- [{m.get('id', '')}] {m.get('subject', '')} from {m.get('from', '')} ({m.get('date', '')})")
            body = m.get("body", "").strip()
            if body:
                lines.append(f"    {body[:200]}")
        return "\n".join(lines)

    async def health_check(self) -> dict:
        if not self.is_configured():
            return {"ok": False, "detail": "Not configured (set EMAIL_IMAP_HOST, EMAIL_SMTP_HOST, EMAIL_USERNAME, EMAIL_PASSWORD)"}
        try:
            conn = self._imap()
            status, _ = conn.select("INBOX", readonly=True)
            conn.logout()
            return {"ok": status == "OK", "detail": f"Connected to {self.imap_host}"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}

    def get_tools(self) -> list[Tool]:
        return [
            service_tool(
                name="send_email",
                description="Send an email to one or more recipients.",
                parameters={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject"},
                        "body": {"type": "string", "description": "Email body text"},
                        "attachments": {"type": "array", "items": {"type": "string"}, "description": "Optional file paths to attach", "default": []},
                    },
                    "required": ["to", "subject", "body"],
                },
                handler=self.send_email,
                category="services",
                permission_level="confirm",
            ),
            service_tool(
                name="read_unread_emails",
                description="Read unread emails from the inbox and summarize them.",
                parameters={
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer", "description": "Number of emails to read", "default": 5},
                    },
                    "required": [],
                },
                handler=self._read_unread_tool,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="search_emails",
                description="Search emails in the inbox by text.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search text"},
                        "count": {"type": "integer", "description": "Number of results", "default": 10},
                    },
                    "required": ["query"],
                },
                handler=self._search_emails_tool,
                category="services",
                permission_level="auto",
            ),
        ]

    async def _read_unread_tool(self, count: int = 5) -> str:
        items = await self.read_unread(count)
        return self.format_email_list(items)

    async def _search_emails_tool(self, query: str, count: int = 10) -> str:
        items = await self.search_emails(query, count)
        return self.format_email_list(items)

    async def close(self) -> None:
        pass
