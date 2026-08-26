"""Adapters, API keys, webhooks, Excel import and the sync log.

Contract tag ``integrations``. Owned by phase-2 task 2E.

Operations this module must implement, from ``docs/openapi.yaml``:
listAdapters, syncAdapter, getAdapterConfig, putAdapterConfig, listApiKeys, createApiKey,
patchApiKey, deleteApiKey, previewExcelImport, createExcelImportRun, listSyncLog, listWebhooks,
createWebhook, patchWebhook, deleteWebhook, testWebhook.

The module and its mount exist before the handlers do so that no phase-2 worker has to edit
``main.py`` or ``routers/__init__.py`` — seven tasks editing one registration list in a shared
working tree is how a mount gets silently dropped. An empty router mounts cleanly and serves
nothing, so this is inert until its owner fills it in.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["integrations"])
