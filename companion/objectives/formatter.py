"""Deterministic template formatting for objective candidates."""

from __future__ import annotations

from companion.objectives.schema import ObjectiveCandidate


def format_objective(candidate: ObjectiveCandidate | None) -> str:
    """Format a single objective into a standard four-part human-readable block.

    Template:
    [<PRIORITY_RANK>] <Objective Title>
    DO NOW: <Specific concrete action to take>
    WHY: <Underlying factual cause and progression impact>
    SOURCE: <Source provenance>
    """
    if candidate is None:
        return (
            "[NO_ACTIONABLE_OBJECTIVE] All current goals met\n"
            "DO NOW: Continue normal gameplay\n"
            "WHY: Character build is synchronized with target recommendations and rules\n"
            "SOURCE: Objective Engine v2"
        )

    lines = [
        f"[{candidate.priority.name}] {candidate.title}",
        f"DO NOW: {candidate.action}",
        f"WHY: {candidate.rationale}",
        f"SOURCE: {candidate.source}",
    ]
    return "\n".join(lines)


def format_objective_list(objectives: list[ObjectiveCandidate]) -> str:
    """Format a list of objectives into a human-readable string separated by boundaries."""
    if not objectives:
        return format_objective(None)

    blocks: list[str] = []
    for idx, obj in enumerate(objectives, start=1):
        block = f"{idx}. {format_objective(obj)}"
        blocks.append(block)

    return "\n\n".join(blocks)
