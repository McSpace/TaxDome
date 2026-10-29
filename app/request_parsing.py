"""Strict parsing of bulk payment request bytes into a validated batch.

The parser works on raw bytes so it can reject what generic JSON tooling silently
accepts: byte-order marks, duplicate member names, NaN/Infinity, implicit type
coercion and unknown attributes. Money is converted to integer cents using integer
arithmetic only.
"""

import json
import re
from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from app.errors import ApiError

MAX_BODY_BYTES = 1_048_576
MAX_BATCH_SIZE = 1000
MAX_DESCRIPTION_CHARS = 1024
MAX_AMOUNT_CHARS = 32
MAX_CENTS = 2_147_483_647

AMOUNT_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]{1,2})?", re.ASCII)
UUID_REGEX = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


@dataclass(frozen=True)
class PaymentEntry:
    payee_firm_uuid: str
    amount_cents: int
    description: str


@dataclass(frozen=True)
class BatchRequest:
    payer_firm_uuid: str
    payments: tuple[PaymentEntry, ...]


def _amount_to_cents(text: str) -> int:
    if len(text) > MAX_AMOUNT_CHARS or not AMOUNT_PATTERN.fullmatch(text):
        raise ValueError(
            "amount must be a positive decimal string with at most 2 fractional digits"
        )
    whole, _, fraction = text.partition(".")
    cents = int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
    if cents < 1:
        raise ValueError("amount must be positive")
    if cents > MAX_CENTS:
        raise ValueError(f"amount must not exceed {MAX_CENTS} cents")
    return cents


def _check_description(text: str) -> str:
    # Lone surrogates never get here: strict str validation rejects them first.
    if "\u0000" in text:
        raise ValueError("description must not contain U+0000")
    return text


Amount = Annotated[str, Field(max_length=MAX_AMOUNT_CHARS), AfterValidator(_amount_to_cents)]
FirmUuid = Annotated[str, Field(pattern=UUID_REGEX), AfterValidator(str.lower)]
Description = Annotated[
    str, Field(max_length=MAX_DESCRIPTION_CHARS), AfterValidator(_check_description)
]


class PaymentRequestEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    # The validator converts the string to integer cents; the wire type stays a string.
    amount: Amount = Field(
        description="USD amount as a string with at most 2 decimal places, e.g. \"1200.75\".",
        examples=["1200.75"],
    )
    payee_firm_uuid: FirmUuid = Field(description="Public UUID of the receiving firm.")
    description: Description = Field(description="Payment description, 0-1024 characters.")


class BatchRequestModel(BaseModel):
    """JSON body of POST /payments/batch."""

    model_config = ConfigDict(strict=True, extra="forbid")

    payer_firm_uuid: FirmUuid = Field(description="Public UUID of the paying firm.")
    payments: list[PaymentRequestEntry] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


def parse_amount(text: str) -> int:
    """Convert a request amount string to integer cents or raise a 422 ApiError."""
    try:
        return _amount_to_cents(text)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from None


def _check_media_type(content_type: str | None) -> None:
    if not content_type:
        raise ApiError(415, "unsupported_media_type", "Content-Type must be application/json.")
    media_type, *params = (part.strip() for part in content_type.split(";"))
    if media_type.lower() != "application/json":
        raise ApiError(415, "unsupported_media_type", "Content-Type must be application/json.")
    for param in params:
        name, _, value = param.partition("=")
        if name.strip().lower() == "charset" and value.strip().strip('"').lower() != "utf-8":
            raise ApiError(415, "unsupported_media_type", "Only the UTF-8 charset is supported.")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate member name {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def _decode_json(body: bytes) -> Any:
    invalid = ApiError(400, "invalid_json", "Request body must be a valid UTF-8 JSON document.")
    if body.startswith(b"\xef\xbb\xbf"):
        raise invalid
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise invalid from None
    if not text.strip():
        raise invalid
    try:
        return json.loads(
            text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant
        )
    except (ValueError, RecursionError):
        raise invalid from None


def _path(loc: tuple[int | str, ...]) -> str:
    path = ""
    for part in loc:
        path += f"[{part}]" if isinstance(part, int) else (f".{part}" if path else str(part))
    return path


def _validation_details(exc: ValidationError) -> list[dict[str, Any]]:
    details = []
    for error in exc.errors(include_url=False, include_input=False):
        loc = error["loc"]
        index = loc[1] if len(loc) > 1 and loc[0] == "payments" and isinstance(loc[1], int) else None
        message = error["msg"].removeprefix("Value error, ")
        details.append({"index": index, "path": _path(loc), "message": message})
    details.sort(key=lambda d: (-1 if d["index"] is None else d["index"], d["path"]))
    return details


def parse_batch_request(body: bytes, content_type: str | None) -> BatchRequest:
    """Parse and fully validate a request body; raise ApiError on the first failing stage."""
    if len(body) > MAX_BODY_BYTES:
        raise ApiError(413, "request_too_large", "Request body exceeds 1 MiB.")
    _check_media_type(content_type)
    document = _decode_json(body)
    try:
        model = BatchRequestModel.model_validate(document)
    except ValidationError as exc:
        raise ApiError(
            422, "validation_error", "Request validation failed.", _validation_details(exc)
        ) from None
    return BatchRequest(
        payer_firm_uuid=model.payer_firm_uuid,
        payments=tuple(
            PaymentEntry(p.payee_firm_uuid, p.amount, p.description)
            for p in model.payments
        ),
    )
