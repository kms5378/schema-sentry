from enum import StrEnum


class ScanStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ScanTrigger(StrEnum):
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"


class ChangeType(StrEnum):
    ADD_COLUMN = "ADD_COLUMN"
    DROP_COLUMN = "DROP_COLUMN"
    TYPE_CHANGE = "TYPE_CHANGE"
    NULLABILITY_CHANGE = "NULLABILITY_CHANGE"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    BREAKING = "BREAKING"


class ChangeState(StrEnum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    RESOLVED = "RESOLVED"


class PipelineCriticality(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertChannel(StrEnum):
    SLACK = "SLACK"
    EMAIL = "EMAIL"


class AlertStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
