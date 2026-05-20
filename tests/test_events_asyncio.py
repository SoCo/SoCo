"""Tests for soco.events_asyncio listener shutdown behavior.

These tests target the EventListener.async_stop() / stop_listening()
shutdown paths to guard against the regressions documented in the
"events_asyncio async_stop race" fix:

  - async_stop() must not raise when the underlying socket has already
    been closed by a concurrent shutdown path (manifests as
    ``ValueError: Invalid file descriptor: -1`` from aiohttp's
    ``SockSite.stop()``).

  - stop_listening() schedules async_stop() as a fire-and-forget task;
    any exception that bubbles out of that task must be consumed so it
    does not surface as ``Task exception was never retrieved``.
"""

import asyncio
import logging
from unittest import mock

import pytest

from soco import events_asyncio


@pytest.mark.asyncio
async def test_async_stop_tolerates_closed_socket(caplog):
    """async_stop must not raise when site.stop() finds a closed fd."""
    listener = events_asyncio.EventListener()
    listener.site = mock.MagicMock()
    listener.site.stop = mock.AsyncMock(
        side_effect=ValueError("Invalid file descriptor: -1")
    )
    listener.runner = mock.MagicMock()
    listener.runner.cleanup = mock.AsyncMock()
    listener.session = mock.MagicMock()
    listener.session.close = mock.AsyncMock()
    listener.sock = mock.MagicMock()
    listener.is_running = True

    with caplog.at_level(logging.DEBUG, logger="soco.events_asyncio"):
        await listener.async_stop()

    # async_stop must run to completion even when site.stop() raises.
    assert listener.is_running is False
    assert listener.site is None
    assert listener.runner is None
    assert listener.session is None
    assert listener.sock is None
    # The error must be logged (at DEBUG) so operators can still diagnose.
    assert any("Invalid file descriptor" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_stop_listening_swallows_task_exception(caplog):
    """The async_stop task scheduled by stop_listening must not surface
    as ``Task exception was never retrieved``.
    """
    listener = events_asyncio.EventListener()
    # Force async_stop to raise so we can verify the spawned task's
    # exception is handled rather than escaping.
    listener.async_stop = mock.AsyncMock(side_effect=RuntimeError("boom"))

    with caplog.at_level(logging.DEBUG, logger="soco.events_asyncio"):
        listener.stop_listening(address=("127.0.0.1", 1400))
        # Yield once so the scheduled task gets to run and the done
        # callback fires.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    listener.async_stop.assert_called_once()
    assert any(
        "async_stop scheduled by stop_listening raised" in r.message
        for r in caplog.records
    )
