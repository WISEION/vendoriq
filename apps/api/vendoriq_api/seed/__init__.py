"""The seed CLI — phase 1E (brief §2, seed/README.md).

``python -m vendoriq_api.seed`` implements the three commands the Makefile wires up:

* ``load --real``  — the 13 real vendors, the category taxonomy, the two scoring models,
  the ``TQS2026006`` qualification cycle and its applications (brief §1.10).
* ``load --demo``  — the removable layer on top: category *assignments*, the 4 demo
  suppliers, the work-package breakdown of both projects, and document expiry dates.
* ``purge-demo``   — deletes every ``is_demo=True`` row the demo layer added.

The package is split by concern rather than by command: ``data.py`` reads and types
``seed/data.json``; ``common.py`` holds the get-or-create helpers both loaders share;
``real.py``, ``demo.py`` and ``purge.py`` are the three commands; ``cli.py`` is the
argument parser and the summary printer.
"""

from __future__ import annotations
