from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalBonusCommand:
    source: str
    message_id: str
    channel: str
    sender_id: str
    sent_at_ms: int
    text: str


@dataclass(frozen=True)
class ParsedBonusCommand:
    kind: str
    name: str
    raw_params: dict
