from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolvedHandler[HandlerT, RegistrationT]:
    handler: HandlerT
    handler_type: type[HandlerT]
    registration: RegistrationT
