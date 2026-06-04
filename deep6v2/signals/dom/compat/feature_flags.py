import os


DOM_INTELLIGENCE_ENABLED_ENV_VAR = "DOM_INTELLIGENCE_ENABLED"


def is_dom_intelligence_enabled() -> bool:
    """
    Check whether the DOM intelligence subsystem is enabled.
    Reads DOM_INTELLIGENCE_ENABLED env var; defaults to True if unset.
    Set DOM_INTELLIGENCE_ENABLED=False to disable all DOM detector registration.
    When disabled: registry behaves exactly as before — zero impact on existing pipeline.
    """
    return os.environ.get(DOM_INTELLIGENCE_ENABLED_ENV_VAR, "true").lower() not in ("false", "0", "no")


def force_enable_dom_intelligence() -> None:
    """Force enable for tests — set env var to 'true'."""
    os.environ[DOM_INTELLIGENCE_ENABLED_ENV_VAR] = "true"


def force_disable_dom_intelligence() -> None:
    """Force disable for rollback testing — set env var to 'false'."""
    os.environ[DOM_INTELLIGENCE_ENABLED_ENV_VAR] = "false"
