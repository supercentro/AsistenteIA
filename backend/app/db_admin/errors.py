"""Errors of the database administration commands; their messages never carry a secret."""


class DbAdminError(RuntimeError):
    """A command failed. The message names the step and the SQLSTATE, never a value."""
