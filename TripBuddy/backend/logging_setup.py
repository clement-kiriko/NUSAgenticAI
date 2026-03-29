import logging
import os

from logging_context import current_audit_id, current_run_id


class AuditAwareFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        raw_audit_id = getattr(record, "audit_id", "")
        raw_run_id = getattr(record, "run_id", "")
        audit_id = str(raw_audit_id or "").strip()
        run_id = str(raw_run_id or "").strip()
        segments = []
        if audit_id and audit_id != "-":
            segments.append(f"audit_id={audit_id}")
        if run_id and run_id != "-":
            segments.append(f"run_id={run_id}")
        record.audit_segment = f" [{' '.join(segments)}]" if segments else ""
        return super().format(record)


class AuditIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "audit_id"):
            record.audit_id = current_audit_id()
        if not hasattr(record, "run_id"):
            record.run_id = current_run_id()
        return True


def configure_logging() -> None:
    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s%(audit_segment)s: %(message)s",
        )
    audit_filter = AuditIdFilter()
    for handler in root_logger.handlers:
        handler.addFilter(audit_filter)
        handler.setFormatter(AuditAwareFormatter(handler.formatter._fmt, handler.formatter.datefmt))

    # Prefer app-owned API wrapper logs over library-level raw HTTP request logs,
    # which can expose sensitive query parameters.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
