"""Tools an agent graph can call, declared once in a registry.

A tool has a name, an input schema (a frozen dataclass) and a handler. The graph decides
when to call a tool; the registry only checks that the tool exists and gets its input type.
The runtime wraps every handler, so each call is a named child run of the traced turn.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from typing import Any


class UnknownToolError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    input_type: type[Any]
    handler: Callable[[Any], Any]

    def __post_init__(self) -> None:
        if not is_dataclass(self.input_type):
            raise TypeError(f"Tool '{self.name}' needs a dataclass input schema.")

    @property
    def input_schema(self) -> Mapping[str, str]:
        """Field name -> type, for docs and tests."""
        return {
            item.name: getattr(item.type, "__name__", None) or str(item.type)
            for item in fields(self.input_type)
        }


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"Tool '{tool.name}' is declared twice.")
            self._tools[tool.name] = tool

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as error:
            raise UnknownToolError(name) from error

    def call(self, name: str, arguments: Any) -> Any:
        tool = self.get(name)
        if not isinstance(arguments, tool.input_type):
            raise TypeError(f"Tool '{name}' expects {tool.input_type.__name__}.")
        return tool.handler(arguments)

    def wrapped(self, wrap: Callable[[Tool], Callable[[Any], Any]]) -> "ToolRegistry":
        """The same tools with each handler replaced by `wrap(tool)` (tracing, metrics)."""
        return ToolRegistry(
            Tool(tool.name, tool.description, tool.input_type, wrap(tool))
            for tool in self._tools.values()
        )
