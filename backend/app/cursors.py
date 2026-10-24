import base64
import hashlib
import hmac
import json
import time

from .errors import AppError
from .models import Query


def encoded(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decoded(raw: str) -> bytes:
    return base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)


class Cursors:
    def __init__(self, key: bytes):
        if len(key) < 32:
            raise ValueError("Cursor key needs at least 32 bytes")
        self.key = key

    def fingerprint(self, tenant: str, dataset: str, query: Query) -> str:
        body = [tenant, dataset, query.model_dump(exclude={"cursor"})]
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    def issue(self, tenant: str, dataset: str, query: Query, release: str, offset: int) -> str:
        raw = encoded(
            json.dumps(
                {
                    "v": 1,
                    "f": self.fingerprint(tenant, dataset, query),
                    "r": release,
                    "o": offset,
                    "exp": int(time.time()) + 900,
                },
                separators=(",", ":"),
            ).encode()
        )
        return raw + "." + encoded(hmac.new(self.key, raw.encode(), hashlib.sha256).digest())

    def read(self, tenant: str, dataset: str, query: Query) -> tuple[str | None, int]:
        if not query.cursor:
            return None, 0
        try:
            raw, signature = query.cursor.split(".")
            expected = hmac.new(self.key, raw.encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(expected, decoded(signature)):
                raise ValueError("signature")
            body = json.loads(decoded(raw))
            if (
                body["v"] != 1
                or body["f"] != self.fingerprint(tenant, dataset, query)
                or body["exp"] < time.time()
                or not isinstance(body["r"], str)
                or type(body["o"]) is not int
                or not 0 <= body["o"] <= 10000
            ):
                raise ValueError("context")
            return body["r"], body["o"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(
                400, "invalid_cursor", "Pagination expired or filters changed. Start from the first page."
            ) from exc
