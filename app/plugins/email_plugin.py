"""Email / notification plugin.

The delivery mechanism is pluggable. The default ``sink`` sender records
messages in memory (safe for dev and tests); production swaps in an SMTP
sender. Nothing is sent over the network by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, EmailStr, Field

from app.domain.plugins import Plugin, PluginContext
from app.plugins.registry import register


@dataclass(slots=True)
class SentMessage:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class SinkEmailSender:
    """Records messages instead of sending them."""

    def __init__(self) -> None:
        self.outbox: list[SentMessage] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.outbox.append(SentMessage(to=to, subject=subject, body=body))


@register
class EmailSendPlugin(Plugin):
    name = "email.send"
    category = "notification"
    summary = "Send (or record) an email/notification message."

    class Params(BaseModel):
        to: EmailStr
        subject: str = Field(min_length=1, max_length=200)
        body: str = ""

    params_model = Params

    def __init__(self) -> None:
        self.sender: EmailSender = SinkEmailSender()

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, EmailSendPlugin.Params)
        await self.sender.send(to=str(params.to), subject=params.subject, body=params.body)
        return {"sent": True, "to": str(params.to), "subject": params.subject}
