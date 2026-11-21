"""Classes and functions for checking for and applying software updates.

A Sonos household shares one update manifest. Each speaker picks its own
target version from that manifest based on its model, submodel and current
software version, so speakers in the same household can be on different
versions and still be up to date.

The update itself is started with the ``BeginSoftwareUpdate`` action of the
``ZoneGroupTopology`` service. On firmware that supports it, the speaker can
report progress while it updates over the Sonos Device Update Control
Protocol (SDUCP), a line based protocol on TCP port 4444.
"""

import logging
import socket
import time
from collections import namedtuple

import requests

from .exceptions import SoCoException
from .xml import XML

_LOG = logging.getLogger(__name__)

UPDATE_NAMESPACE = "{urn:schemas-rinconnetworks-com:update-1-0}"

#: The speaker drives the update and reports progress to any client
#: connected to the SDUCP port. Requires recent firmware.
FLAG_PROGRESS_MONITORED = 0x40

SDUCP_PORT = 4444

UpdateItem = namedtuple(
    "UpdateItem", ["version", "update_url", "manifest_url", "manifest_revision"]
)
UpdateItem.__doc__ = """The household update offered by a speaker.

Attributes:
    version (str): The household's target software version.
    update_url (str): The base URL for the household's target version.
    manifest_url (str): The URL of the update manifest.
    manifest_revision (str): The revision of the update manifest.
"""

UpdateStatus = namedtuple(
    "UpdateStatus", ["installed_version", "latest_version", "update_url"]
)
UpdateStatus.__doc__ = """The update status of one speaker.

Attributes:
    installed_version (str): The software version the speaker is running.
    latest_version (str): The version the manifest targets for this speaker.
    update_url (str): The URL to pass to
        :meth:`~soco.core.SoCo.begin_software_update` for this speaker.
"""

UpdateProgress = namedtuple("UpdateProgress", ["phase", "percent"])
UpdateProgress.__doc__ = """Progress reported by a speaker during an update.

Attributes:
    phase (str): The update phase, ``DOWNLOAD``, ``FLASHWRITE`` or
        ``REBOOT``.
    percent (int): Overall progress of the update, from 0 to 100.
"""


class SoftwareUpdateError(SoCoException):
    """Raised when a speaker reports that its software update failed."""

    def __init__(self, phase, error_code, detail=None):
        super().__init__(
            "Update failed in phase {} with error code {}{}".format(
                phase, error_code, ": {}".format(detail) if detail else ""
            )
        )
        self.phase = phase
        self.error_code = error_code
        self.detail = detail


def parse_version(version):
    """Convert a Sonos software version string to a comparable tuple.

    Args:
        version (str): A version like ``97.2-81220``.

    Returns:
        tuple: ``(97, 2, 81220)``, or `None` if the version can't be parsed.
    """
    try:
        major_minor, build = version.split("-")
        major, minor = major_minor.split(".")
        return int(major), int(minor), int(build)
    except (AttributeError, ValueError):
        return None


def parse_hardware_version(hardware_version):
    """Get the model and submodel from a speaker's hardware version.

    Args:
        hardware_version (str): The ``hardware_version`` from
            :meth:`~soco.core.SoCo.get_speaker_info`, like ``1.33.1.8-1.9``.

    Returns:
        tuple: ``(model, submodel)`` as ints, like ``(33, 1)``.
    """
    parts = hardware_version.split("-")[0].split(".")
    return int(parts[1]), int(parts[2])


def parse_update_item(update_item):
    """Parse the ``UpdateItem`` returned by ``CheckForUpdate``.

    Args:
        update_item (str): The ``UpdateItem`` XML.

    Returns:
        UpdateItem: The parsed item, or `None` if no update is offered.
    """
    if not update_item:
        return None
    item = XML.fromstring(update_item.encode("utf-8"))
    if not item.get("Version"):
        return None
    return UpdateItem(
        item.get("Version"),
        item.get("UpdateURL"),
        item.get("ManifestURL"),
        item.get("ManifestRevision"),
    )


class UpdateManifest:
    """A Sonos update manifest (``update.upm``)."""

    def __init__(self, default_version, base_url, images):
        """
        Args:
            default_version (str): The version for models with no image entry.
            base_url (str): The URL for models with no image entry.
            images (list): The manifest's image entries as dicts of their
                attributes, with the image URL under ``url``.
        """
        self.default_version = default_version
        self.base_url = base_url
        self.images = images

    @classmethod
    def from_xml(cls, xml):
        """Parse a manifest.

        Args:
            xml (bytes): The manifest XML.

        Returns:
            UpdateManifest: The parsed manifest.
        """
        root = XML.fromstring(xml)
        images = []
        for image in root.iter("image"):
            attrs = dict(image.attrib)
            attrs["url"] = (image.text or "").strip()
            images.append(attrs)
        return cls(root.get("default_version"), root.get("base_url"), images)

    @classmethod
    def fetch(cls, url, timeout=None):
        """Download and parse a manifest.

        Args:
            url (str): The ``manifest_url`` of an :class:`UpdateItem`.
            timeout: Passed to `requests.get`.

        Returns:
            UpdateManifest: The parsed manifest.
        """
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return cls.from_xml(response.content)

    def target(self, model, submodel, current_version):
        """Find the version and URL the manifest targets for a speaker.

        This follows the speaker firmware: the last image entry for the model
        whose ``fromver`` range includes the current version wins, and an
        entry whose submodel range matches beats one with no submodel range.
        Models with no matching entry get the manifest's default version.

        Args:
            model (int): The speaker's model, from
                :func:`parse_hardware_version`.
            submodel (int): The speaker's submodel.
            current_version (str): The speaker's software version.

        Returns:
            tuple: ``(version, url)``.
        """
        version, url = self.default_version, self.base_url
        current = parse_version(current_version)
        submodel_matched = False
        for image in self.images:
            if image.get("model") != str(model):
                continue
            # Entries for a specific arch or component (Android based
            # products) aren't handled.
            if image.get("arch", "default") != "default" or image.get("component"):
                continue
            fromver_min = parse_version(image.get("fromver_min"))
            fromver_max = parse_version(image.get("fromver_max"))
            if fromver_min and (current is None or current < fromver_min):
                continue
            if fromver_max and (current is None or current > fromver_max):
                continue
            if "submodel_min" in image:
                if not (
                    int(image["submodel_min"])
                    <= submodel
                    <= int(image.get("submodel_max", image["submodel_min"]))
                ):
                    continue
                submodel_matched = True
            elif submodel_matched:
                continue
            version, url = image.get("version"), image["url"] or self.base_url
        return version, url


def monitor_update(ip_address, timeout=60, connect_timeout=300):
    """Read the progress of a monitored update from a speaker.

    Start the update with :meth:`~soco.core.SoCo.begin_software_update` and
    the :data:`FLAG_PROGRESS_MONITORED` flag first. The speaker closes the
    connection when it reboots into the new version. The update carries on
    if the connection drops, so a failure to connect or read doesn't mean
    the update failed.

    The speaker only listens for monitoring connections once its upgrade has
    started, which can take from ten seconds to a couple of minutes after
    :meth:`~soco.core.SoCo.begin_software_update` returns, so connecting is
    retried until ``connect_timeout``.

    Args:
        ip_address (str): The speaker's IP address.
        timeout (float): Socket timeout in seconds.
        connect_timeout (float): How long to keep trying to connect, in
            seconds.

    Yields:
        UpdateProgress: Each progress report.

    Raises:
        SoftwareUpdateError: If the speaker reports that the update failed.
    """
    with _connect(ip_address, timeout, connect_timeout) as sock:
        for line in sock.makefile("r", encoding="utf-8", newline="\n"):
            command, _, args = line.strip().partition("?")
            params = dict(arg.split("=", 1) for arg in args.split(";") if "=" in arg)
            _LOG.debug("SDUCP from %s: %s", ip_address, line.strip())
            if command == "STATUS":
                yield UpdateProgress(
                    params.get("phase"), int(params.get("percent-complete", 0))
                )
            elif command == "ERROR":
                raise SoftwareUpdateError(
                    params.get("phase"),
                    params.get("error-code"),
                    params.get("internal-data"),
                )


def _connect(ip_address, timeout, connect_timeout):
    """Connect to a speaker's SDUCP port, retrying until it accepts."""
    deadline = time.monotonic() + connect_timeout
    while True:
        try:
            return socket.create_connection((ip_address, SDUCP_PORT), timeout=timeout)
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.5)
