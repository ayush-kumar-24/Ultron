"""Feature modules — application use cases and orchestration logic.

Each subpackage maps to a VISION.md architectural module. Modules depend
on ``core`` interfaces and delegate I/O to ``infrastructure`` adapters.
They must not import PySide6 widgets directly; UI talks to modules via
controllers and the event bus.
"""
