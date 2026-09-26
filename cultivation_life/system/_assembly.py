"""Assemble source-only method containers without changing a system's MRO."""

from __future__ import annotations

from types import FunctionType
from typing import Any


def include_system_methods(*components: type, namespace: dict[str, Any]):
    """Keep moved methods in their original class and module global namespace.

    Component classes only hold method source. Their dependencies are declared
    under TYPE_CHECKING; runtime lookup uses the original system module, including
    its replaceable globals and module-level helpers.
    """
    def decorate(target: type) -> type:
        for component in components:
            for name, member in vars(component).items():
                if name.startswith("__"):
                    continue
                if name in vars(target):
                    raise RuntimeError(f"duplicate {target.__name__} method: {name}")
                descriptor = None
                function = member
                if isinstance(member, staticmethod):
                    descriptor = staticmethod
                    function = member.__func__
                elif isinstance(member, classmethod):
                    descriptor = classmethod
                    function = member.__func__
                if not isinstance(function, FunctionType):
                    raise TypeError(f"{component.__name__}.{name} must be a method")
                rebound = FunctionType(
                    function.__code__, namespace, function.__name__,
                    function.__defaults__, function.__closure__,
                )
                rebound.__kwdefaults__ = function.__kwdefaults__
                rebound.__annotations__ = dict(function.__annotations__)
                rebound.__dict__.update(function.__dict__)
                rebound.__doc__ = function.__doc__
                rebound.__module__ = target.__module__
                rebound.__qualname__ = f"{target.__qualname__}.{name}"
                if hasattr(function, "__type_params__"):
                    rebound.__type_params__ = function.__type_params__
                setattr(target, name, descriptor(rebound) if descriptor else rebound)
        return target
    return decorate
