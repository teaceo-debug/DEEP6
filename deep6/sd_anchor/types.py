"""Shared types for the Standard Deviation Anchor AI system.

Placing HermesVerdict here breaks the circular import between
sidecar.py (which defines the bridge) and hermes_workflow.py
(which implements the reviewer).
"""

from __future__ import annotations

from dataclasses import dataclass, field

_VALID_VERDICTS = frozenset({"approve", "veto", "abstain"})


@dataclass
class HermesVerdict:
    """Immutable result from a HERMES review cycle.

    Attributes:
        verdict: One of ``approve``, ``veto``, ``abstain``.
        reasons: Non-empty list of reason codes from the authority contract.
        version: HERMES skill/model version that produced this verdict.
        timestamp: ISO 8601 timestamp of the verdict.
    """

    verdict: str
    reasons: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    timestamp: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"Invalid verdict {self.verdict!r}; must be one of {_VALID_VERDICTS}"
            )
