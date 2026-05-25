"""Tests for soco.events_asyncio listener shutdown behavior.

These tests target the EventListener.async_stop() / stop_listening()
shutdown paths to guard against two regression families:

  1. Race tolerance — async_stop() must not raise when the underlying
     socket has already been closed by a concurrent shutdown path
     (manifests as ``ValueError: Invalid file descriptor: -1`` from
     aiohttp's ``SockSite.stop()``), and exceptions from the task
     spawned by stop_listening() must not surface as
     ``Task exception was never retrieved``.

  2. Deferred stop / refcounting — stop_listening() defers the actual
     teardown by a short grace window. A resubscribe inside that window
     cancels the pending stop and reuses the running HTTP server. This
     eliminates teardown/rebuild churn (and the FD races above) on
     every renew cycle.
"""

import asyncio
import logging
from unittest import mock

import pytest

# ``soco.events_asyncio`` imports aiohttp at module load. Skip the entire
# test module when aiohttp isn't available so SoCo's default test job
# (which doesn't install the optional asyncio stack) still passes.
pytest.importorskip("aiohttp")

from soco import events_asyncio  # noqa: E402

# --------------------------------------------------------------------------
# Shared fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def restore_subscriptions_map():
    """Snapshot ``events_asyncio.subscriptions_map`` state, restore after.

    Tests that mutate the module-level subscriptions map (to control which
    branch of ``_deferred_stop`` runs) use this fixture so a mid-test
    failure cannot leak state into subsequent tests in the module.

    The fixture starts the test from a cleared state and yields the map
    for convenience; the ``finally`` clause restores the snapshot
    regardless of test outcome.
    """
    smap = events_asyncio.subscriptions_map
    saved_subs = dict(smap.subscriptions)
    try:
        smap.subscriptions.clear()
        yield smap
    finally:
        smap.subscriptions.clear()
        smap.subscriptions.update(saved_subs)


# --------------------------------------------------------------------------
# Race tolerance — original band-aid behavior
# --------------------------------------------------------------------------


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
async def test_stop_listening_swallows_task_exception(
    caplog, restore_subscriptions_map
):
    """An exception raised by the deferred async_stop must not surface as
    ``Task exception was never retrieved`` — the done-callback must
    consume it and log at DEBUG.
    """
    listener = events_asyncio.EventListener()
    # Short-circuit the grace window so the deferred task runs promptly.
    listener._stop_grace_seconds = 0.01
    # Force async_stop to raise so we can verify the spawned task's
    # exception is handled rather than escaping.
    listener.async_stop = mock.AsyncMock(side_effect=RuntimeError("boom"))
    # restore_subscriptions_map starts in a cleared state so the deferred
    # stop will actually invoke async_stop.

    with caplog.at_level(logging.DEBUG, logger="soco.events_asyncio"):
        listener.stop_listening(address=("127.0.0.1", 1400))
        # Wait long enough for the grace window + the async_stop body.
        await asyncio.sleep(0.1)

    listener.async_stop.assert_awaited_once()
    assert any(
        "async_stop scheduled by stop_listening raised" in r.message
        for r in caplog.records
    )


# --------------------------------------------------------------------------
# Deferred stop / refcounting — Option B behavior
# --------------------------------------------------------------------------


def _populate_running_listener(listener):
    """Set up a listener with the runtime resources of a started server."""
    listener.is_running = True
    listener.site = mock.MagicMock()
    listener.site.stop = mock.AsyncMock()
    listener.runner = mock.MagicMock()
    listener.runner.cleanup = mock.AsyncMock()
    listener.session = mock.MagicMock()
    listener.session.close = mock.AsyncMock()
    listener.sock = mock.MagicMock()


@pytest.mark.asyncio
async def test_async_start_cancels_pending_deferred_stop_and_resumes():
    """A resubscribe within the grace window cancels the deferred stop
    and resumes the listener without tearing anything down — this is the
    fast path that eliminates teardown/rebuild churn on every renew."""
    listener = events_asyncio.EventListener()
    _populate_running_listener(listener)
    listener._stop_grace_seconds = 1.0

    # The base class sets is_running=False before calling stop_listening,
    # so model that here.
    listener.is_running = False
    listener.stop_listening(address=("127.0.0.1", 1400))
    pending_task = listener._stop_grace_task
    assert pending_task is not None
    assert not pending_task.done()

    # Simulate a fresh subscribe inside the grace window.
    any_zone = mock.MagicMock()
    any_zone.ip_address = "127.0.0.1"
    await listener.async_start(any_zone)

    # The deferred stop should have been cancelled and the listener resumed.
    assert listener._stop_grace_task is None
    assert listener.is_running is True
    # Resources untouched — no teardown happened.
    listener.site.stop.assert_not_called()
    listener.runner.cleanup.assert_not_called()
    listener.session.close.assert_not_called()
    # Let the cancellation settle so pytest-asyncio doesn't warn.
    await asyncio.sleep(0)
    assert pending_task.cancelled()


@pytest.mark.asyncio
async def test_deferred_stop_runs_when_grace_expires_and_count_zero(
    restore_subscriptions_map,
):
    """If no resubscribe arrives during the grace window and the
    subscription map is empty, the deferred stop actually runs."""
    listener = events_asyncio.EventListener()
    _populate_running_listener(listener)
    listener._stop_grace_seconds = 0.01

    # restore_subscriptions_map ensures count == 0 so the deferred stop fires.

    # Capture mock references — async_stop will set the attrs to None.
    site_mock = listener.site
    runner_mock = listener.runner
    session_mock = listener.session

    listener.stop_listening(address=("127.0.0.1", 1400))
    # Wait past the grace window plus the async_stop body.
    await asyncio.sleep(0.1)

    site_mock.stop.assert_awaited_once()
    runner_mock.cleanup.assert_awaited_once()
    session_mock.close.assert_awaited_once()
    assert listener.is_running is False
    assert listener.site is None
    assert listener.sock is None


@pytest.mark.asyncio
async def test_deferred_stop_aborts_when_subscription_appears_in_grace(
    caplog,
    restore_subscriptions_map,
):
    """If a subscription appears during the grace window — even without
    a corresponding async_start — the deferred stop must abort."""
    listener = events_asyncio.EventListener()
    _populate_running_listener(listener)
    listener._stop_grace_seconds = 0.05

    listener.stop_listening(address=("127.0.0.1", 1400))

    # Insert a fake subscription before the grace expires. The fixture
    # restores the map after the test regardless of outcome.
    fake_sub = mock.MagicMock()
    fake_sub.sid = "uuid:fake-1"
    restore_subscriptions_map.subscriptions[fake_sub.sid] = fake_sub

    with caplog.at_level(logging.DEBUG, logger="soco.events_asyncio"):
        await asyncio.sleep(0.15)

    # Stop must NOT have run; resources stay intact.
    listener.site.stop.assert_not_called()
    listener.runner.cleanup.assert_not_called()
    listener.session.close.assert_not_called()
    assert any("deferred stop aborted" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_async_stop_idempotent_under_parallel_calls():
    """Two overlapping async_stop calls must not double-close; the
    stop_lock serializes them and the second sees cleared attrs."""
    listener = events_asyncio.EventListener()
    _populate_running_listener(listener)
    site_mock = listener.site
    runner_mock = listener.runner
    session_mock = listener.session
    sock_mock = listener.sock

    await asyncio.gather(listener.async_stop(), listener.async_stop())

    # Each underlying close was invoked exactly once.
    site_mock.stop.assert_awaited_once()
    runner_mock.cleanup.assert_awaited_once()
    session_mock.close.assert_awaited_once()
    sock_mock.close.assert_called_once()
    assert listener.is_running is False
