"""The market-intelligence views.

Contract tag ``intel``. Owned by phase-2 task 2D.

Operations this module must implement, from ``docs/openapi.yaml``:
getIntelOverview, getIntelCoverage, getIntelCapacity, getIntelCertification, getIntelSources,
getIntelGaps, getIntelAttention, getIntelClassDistribution, getExpiringDocuments.

The module and its mount exist before the handlers do so that no phase-2 worker has to edit
``main.py`` or ``routers/__init__.py`` — seven tasks editing one registration list in a shared
working tree is how a mount gets silently dropped. An empty router mounts cleanly and serves
nothing, so this is inert until its owner fills it in.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["intel"])
