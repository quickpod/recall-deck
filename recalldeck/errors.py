"""Error types for recalldeck."""


class RecallDeckError(Exception):
    """Raised for any recoverable failure in a recalldeck operation.

    Every public function raises this (and only this) on failure so callers --
    including the CLI and the GUI -- have a single exception to catch and can
    surface a clean message instead of a raw traceback.
    """
