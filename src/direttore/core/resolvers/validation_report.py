from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from os import PathLike
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DependencyResolutionDescription:
    parameter_name: str
    dependency_name: str
    source: str
    implementation_name: str


@dataclass(frozen=True, slots=True)
class HandlerResolutionDescription:
    context_name: str
    handler_kind: str
    handler_name: str
    is_cached: bool
    key: str | None
    saga_key: str | None
    dependencies: tuple[DependencyResolutionDescription, ...]


def write_validation_report(
    path: str | PathLike[str],
    descriptions: list[HandlerResolutionDescription],
    *,
    context_names: Iterable[str] = (),
) -> None:
    report_path = Path(path)
    report_path.write_text(
        _render_validation_report(
            descriptions,
            context_names=context_names,
        ),
        encoding="utf-8",
    )


def _render_validation_report(
    descriptions: list[HandlerResolutionDescription],
    *,
    context_names: Iterable[str],
) -> str:
    descriptions_by_context: dict[str, list[HandlerResolutionDescription]] = {
        context_name: [] for context_name in context_names
    }
    for description in descriptions:
        descriptions_by_context.setdefault(description.context_name, []).append(
            description
        )

    lines: list[str] = []
    for context_name, context_descriptions in descriptions_by_context.items():
        if lines and lines[-1]:
            lines.append("")

        lines.append(f"# Context: {context_name}")
        if not context_descriptions:
            lines.extend(["", "Handlers: none"])
            continue

        descriptions_by_kind: dict[str, list[HandlerResolutionDescription]] = {}
        for description in context_descriptions:
            descriptions_by_kind.setdefault(description.handler_kind, []).append(
                description
            )

        for handler_kind, kind_descriptions in descriptions_by_kind.items():
            if lines and lines[-1]:
                lines.append("")
            lines.extend([f"## {_handler_kind_heading(handler_kind)}", ""])
            for handler_number, description in enumerate(
                kind_descriptions,
                start=1,
            ):
                lines.extend(
                    [
                        f"{handler_number}. Handler: {description.handler_name}",
                        (
                            "   Cache: application (cached)"
                            if description.is_cached
                            else "   Cache: execution (not cached)"
                        ),
                    ]
                )

                if description.key is not None:
                    lines.append(f"   Registered by key: {description.key}")
                if description.saga_key is not None:
                    lines.append(
                        f"   Registered by saga key: {description.saga_key}"
                    )

                if not description.dependencies:
                    lines.extend(["   Dependencies: none", ""])
                    continue

                lines.append("   Dependencies:")
                for dependency in description.dependencies:
                    lines.append(
                        "   - "
                        f"{dependency.parameter_name}: {dependency.dependency_name}"
                    )
                    lines.append(f"     Source: {dependency.source}")
                    lines.append(
                        f"     Implementation: {dependency.implementation_name}"
                    )
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _handler_kind_heading(handler_kind: str) -> str:
    if handler_kind == "use case":
        return "Use case handlers"
    if handler_kind == "event":
        return "Event handlers"
    return f"{handler_kind.capitalize()} handlers"
