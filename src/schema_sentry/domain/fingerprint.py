import hashlib
import json

from schema_sentry.domain.models import SchemaChange


def change_fingerprint(source_key: str, change: SchemaChange) -> str:
    payload = {"source": source_key, "change": change.to_canonical_dict()}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
