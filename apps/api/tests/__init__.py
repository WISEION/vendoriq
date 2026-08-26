"""Test package for ``apps/api``.

This file exists for one reason: without it mypy resolves both ``apps/api/tests/conftest.py``
and ``packages/excel_import/tests/conftest.py`` to a top-level module called ``conftest`` and
refuses to check the repository ("Duplicate module named conftest"). Making this directory a
package gives its modules a distinct prefix. pytest keeps importing them exactly as before —
``apps/api`` is already on ``sys.path`` through the workspace ``.pth`` file.
"""
