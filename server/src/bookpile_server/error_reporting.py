from typing import Any

import sentry_sdk

from .config import Settings


PRIVATE_EVENT_FIELDS = {
    "breadcrumbs",
    "contexts",
    "extra",
    "logentry",
    "message",
    "request",
    "server_name",
    "threads",
    "user",
}


def scrub_error_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Reduce an error event to technical stack data and BOOKPILE tags."""
    for field in PRIVATE_EVENT_FIELDS:
        event.pop(field, None)

    exception = event.get("exception")
    if isinstance(exception, dict):
        values = exception.get("values")
        if isinstance(values, list):
            for value in values:
                if isinstance(value, dict):
                    value["value"] = "[redacted]"

    tags = event.get("tags")
    if isinstance(tags, dict):
        event["tags"] = {
            key: value
            for key, value in tags.items()
            if str(key).startswith("bookpile.")
        }
    event["transaction"] = "unhandled_request"
    return event


def initialize_error_reporting(settings: Settings) -> bool:
    if settings.error_reporting_dsn is None:
        return False
    sentry_sdk.init(
        dsn=settings.error_reporting_dsn.get_secret_value(),
        environment=settings.environment,
        release=settings.deployment_revision,
        sample_rate=1.0,
        traces_sample_rate=0.0,
        default_integrations=False,
        auto_enabling_integrations=False,
        send_default_pii=False,
        max_breadcrumbs=0,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=scrub_error_event,
    )
    return sentry_sdk.is_initialized()


def capture_unhandled_request_error(
    error: Exception,
    request_id: str,
    settings: Settings,
) -> str | None:
    return capture_unhandled_error(
        error,
        correlation_id=request_id,
        component="api",
        settings=settings,
    )


def capture_unhandled_error(
    error: Exception,
    *,
    correlation_id: str,
    component: str,
    settings: Settings,
) -> str | None:
    if settings.error_reporting_dsn is None:
        return None
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("bookpile.correlation_id", correlation_id)
        scope.set_tag("bookpile.component", component)
        scope.set_tag("bookpile.deployment_revision", settings.deployment_revision)
        return sentry_sdk.capture_exception(error)
