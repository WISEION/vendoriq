"""The one exception this package raises on its own purpose (brief: "fail loudly").

Everything else the loaders hit — a bad path, a database error — is left to propagate as
whatever it already is; wrapping those would only hide where they came from. A
:class:`SeedError` marks the two situations that are the seed's own to catch: a recomputed
Rev4 total that does not match the sheet, and a command run out of the documented order
(``load --demo`` before ``load --real``).
"""

from __future__ import annotations


class SeedError(RuntimeError):
    """A seed invariant failed. ``cli.py`` catches this and exits 1 with the message."""
