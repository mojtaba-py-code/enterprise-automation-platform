"""Plugin package.

Importing this package imports every plugin module, and each module registers
its plugins with the default registry as a side effect. That is the whole of
plugin "discovery" — dropping a new module in here and importing it is enough.
"""

from app.plugins import (  # noqa: F401 - imported for their registration side effects
    email_plugin,
    excel_plugin,
    file_plugin,
    http_plugin,
    pdf_plugin,
    transform_plugin,
)
from app.plugins.registry import PluginRegistry, default_registry, register

__all__ = ["PluginRegistry", "default_registry", "register"]
