"""Errors shared by every app."""


class UserError(ValueError):
    """Something the user can fix. Its message is translated and shown to them as it is."""
