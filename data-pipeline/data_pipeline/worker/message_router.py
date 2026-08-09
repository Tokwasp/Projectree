"""Route one SQS body to the message contract that actually describes it.

Two producers write to this queue:

* AWS S3 ObjectCreated notifications  -> :mod:`s3_events`
* OpenVidu/LiveKit egress completions -> :mod:`openvidu_events`

The router discriminates on body shape and reports *which* contract rejected a
message, so an unparseable body is never reduced to a single vague JSON error.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .errors import UnsupportedMessageError
from .openvidu_events import (
    OpenViduEgressEventParser,
    looks_like_openvidu_egress,
)
from .openvidu_ingest import OpenViduIngestAdapter
from .s3_events import S3EventParser, S3ObjectRecord

logger = logging.getLogger(__name__)

S3_EVENT_CONTRACT = "s3-object-created"
OPENVIDU_CONTRACT = "openvidu-egress"


@dataclass(frozen=True)
class RoutedMessage:
    """Records to ingest, plus the contract that produced them."""

    contract: str
    records: tuple[S3ObjectRecord, ...]
    is_test_event: bool = False


@dataclass(frozen=True)
class SqsMessageRouter:
    """Select the parser for a body and produce ingestible records."""

    s3_parser: S3EventParser
    openvidu_parser: OpenViduEgressEventParser | None = None
    openvidu_adapter: OpenViduIngestAdapter | None = None

    @property
    def openvidu_enabled(self) -> bool:
        return self.openvidu_parser is not None and self.openvidu_adapter is not None

    def route(self, body: str) -> RoutedMessage:
        payload = self._load(body)

        if isinstance(payload, dict) and (
            "Records" in payload or payload.get("Event") == "s3:TestEvent"
        ):
            parsed = self.s3_parser.parse(body)
            return RoutedMessage(
                contract=S3_EVENT_CONTRACT,
                records=parsed.records,
                is_test_event=parsed.is_test_event,
            )

        if looks_like_openvidu_egress(payload):
            if not self.openvidu_enabled:
                raise UnsupportedMessageError(
                    "An OpenVidu egress message was received but OpenVidu "
                    "ingestion is not configured "
                    "(set OPENVIDU_RECORDING_BUCKET and a MeetingContextResolver)"
                )
            event = self.openvidu_parser.parse_payload(payload)
            logger.info(
                "contract=%s stage=parse status=success room=%s egress_id=%s key=%s",
                OPENVIDU_CONTRACT,
                event.room_name,
                event.egress_id,
                event.object_key,
            )
            record = self.openvidu_adapter.to_record(event)
            return RoutedMessage(
                contract=OPENVIDU_CONTRACT,
                records=(record,),
            )

        raise UnsupportedMessageError(
            "SQS body matches no known message contract "
            f"(known: {S3_EVENT_CONTRACT}, {OPENVIDU_CONTRACT}); "
            f"top-level keys: {self._describe_keys(payload)}"
        )

    @staticmethod
    def _load(body: str) -> object:
        try:
            return json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise UnsupportedMessageError(
                "SQS body is not valid JSON"
            ) from exc

    @staticmethod
    def _describe_keys(payload: object) -> str:
        if not isinstance(payload, dict):
            return type(payload).__name__
        # Key names only. Values may contain meeting content and are never logged.
        return ",".join(sorted(payload)[:12]) or "<empty object>"


__all__ = [
    "OPENVIDU_CONTRACT",
    "RoutedMessage",
    "S3_EVENT_CONTRACT",
    "SqsMessageRouter",
]
