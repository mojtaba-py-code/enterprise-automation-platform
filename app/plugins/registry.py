"""Plugin registry.

Plugins self-register with the module-level :data:`default_registry` via the
``@register`` decorator; importing the :mod:`app.plugins` package is enough to
discover them all. Plugins can be enabled or disabled at runtime without
touching the core.
"""

from __future__ import annotations

from app.core.errors import NotFoundError
from app.domain.plugins import Plugin


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._disabled: set[str] = set()

    def add(self, plugin: Plugin) -> None:
        if plugin.name in self._plugins:
            raise ValueError(f"duplicate plugin name: {plugin.name!r}")
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Plugin:
        plugin = self._plugins.get(name)
        if plugin is None:
            raise NotFoundError(f"unknown plugin: {name!r}")
        if name in self._disabled:
            raise NotFoundError(f"plugin is disabled: {name!r}")
        return plugin

    def all(self) -> list[Plugin]:
        return sorted(self._plugins.values(), key=lambda p: p.name)

    def names(self) -> list[str]:
        return sorted(self._plugins)

    def is_enabled(self, name: str) -> bool:
        return name in self._plugins and name not in self._disabled

    def enable(self, name: str) -> None:
        if name not in self._plugins:
            raise NotFoundError(f"unknown plugin: {name!r}")
        self._disabled.discard(name)

    def disable(self, name: str) -> None:
        if name not in self._plugins:
            raise NotFoundError(f"unknown plugin: {name!r}")
        self._disabled.add(name)


default_registry = PluginRegistry()


def register(plugin_cls: type[Plugin]) -> type[Plugin]:
    """Class decorator that instantiates a plugin and registers it."""
    default_registry.add(plugin_cls())
    return plugin_cls
