# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance,no-else-continue

"""This module contains classes relating to Third Party music services."""


import logging
import weakref

import requests

from .. import config, discovery
from ..xml import XML

log = logging.getLogger(__name__)  # pylint: disable=C0103


class Account:
    """An account for a Music Service.

    Each service may have more than one account: see the `Sonos release notes
    for version 5-2 <http://www.sonos.com/en-gb/software/release/5-2>`_
    """

    _all_accounts = weakref.WeakValueDictionary()

    def __init__(self):
        super().__init__()
        #: str: A unique identifier for the music service to which this
        #: account relates, eg ``'2311'`` for Spotify.
        self.service_type = ""
        #: str: A unique identifier for this account
        self.serial_number = ""
        #: str: The account's nickname
        self.nickname = ""
        #: bool: `True` if this account has been deleted
        self.deleted = False
        #: str: The username used for logging into the music service
        self.username = ""
        #: str: Metadata for the account
        self.metadata = ""
        #: str: Used for OpenAuth id for some services
        self.oa_device_id = ""
        #: str: Used for OpenAuthid for some services
        self.key = ""

    def __repr__(self):
        return "<{} '{}:{}:{}' at {}>".format(
            self.__class__.__name__,
            self.serial_number,
            self.service_type,
            self.nickname,
            hex(id(self)),
        )

    def __str__(self):
        return self.__repr__()

    @staticmethod
    def _get_account_xml(soco):
        """Fetch the account data from a Sonos device.

        Args:
            soco (SoCo): a SoCo instance to query. If soco is `None`, a
                random device will be used.

        Returns:
            str: a byte string containing the account data xml
        """
        # It is likely that the same information is available over UPnP as well
        # via a call to
        # systemProperties.GetStringX([('VariableName','R_SvcAccounts')]))
        # This returns an encrypted string, and, so far, we cannot decrypt it
        device = soco or discovery.any_soco()
        log.debug("Fetching account data from %s", device)
        settings_url = "http://{}:1400/status/accounts".format(device.ip_address)
        result = requests.get(settings_url, timeout=config.REQUEST_TIMEOUT).content
        log.debug("Account data: %s", result)
        return result

    @classmethod
    def get_accounts(cls, soco=None):
        """Get all accounts known to the Sonos system.

        Args:
            soco (`SoCo`, optional): a `SoCo` instance to query. If `None`, a
                random instance is used. Defaults to `None`.

        Returns:
            dict: A dict containing account instances. Each key is the
            account's serial number, and each value is the related Account
            instance. Accounts which have been marked as deleted are excluded.

        Note:
            Any existing Account instance will have its attributes updated
            to those currently stored on the Sonos system.
        """

        root = XML.fromstring(cls._get_account_xml(soco))
        # _get_account_xml returns an ElementTree element like this:

        # <ZPSupportInfo type="User">
        #   <Accounts
        #   LastUpdateDevice="RINCON_000XXXXXXXX400"
        #   Version="8" NextSerialNum="5">
        #     <Account Type="2311" SerialNum="1">
        #         <UN>12345678</UN>
        #         <MD>1</MD>
        #         <NN></NN>
        #         <OADevID></OADevID>
        #         <Key></Key>
        #     </Account>
        #     <Account Type="41735" SerialNum="3" Deleted="1">
        #         <UN></UN>
        #         <MD>1</MD>
        #         <NN>Nickname</NN>
        #         <OADevID></OADevID>
        #         <Key></Key>
        #     </Account>
        # ...
        #   <Accounts />

        xml_accounts = root.findall(".//Account")
        result = {}
        for xml_account in xml_accounts:
            serial_number = xml_account.get("SerialNum")
            is_deleted = xml_account.get("Deleted") == "1"
            # cls._all_accounts is a weakvaluedict keyed by serial number.
            # We use it as a database to store details of the accounts we
            # know about. We need to update it with info obtained from the
            # XML just obtained, so (1) check to see if we already have an
            # entry in cls._all_accounts for the account we have found in
            # XML; (2) if so, delete it if the XML says it has been deleted;
            # and (3) if not, create an entry for it
            if cls._all_accounts.get(serial_number):
                # We have an existing entry in our database. Do we need to
                # delete it?
                if is_deleted:
                    # Yes, so delete it and move to the next XML account
                    del cls._all_accounts[serial_number]
                    continue
                else:
                    # No, so load up its details, ready to update them
                    account = cls._all_accounts.get(serial_number)
            else:
                # We have no existing entry for this account
                if is_deleted:
                    # but it is marked as deleted, so we don't need one
                    continue
                # If it is not marked as deleted, we need to create an entry
                account = Account()
                account.serial_number = serial_number
                cls._all_accounts[serial_number] = account

            # Now, update the entry in our database with the details from XML
            account.service_type = xml_account.get("Type")
            account.deleted = is_deleted
            account.username = xml_account.findtext("UN")
            # Not sure what 'MD' stands for.  Metadata? May Delete?
            account.metadata = xml_account.findtext("MD")
            account.nickname = xml_account.findtext("NN")
            account.oa_device_id = xml_account.findtext("OADevID")
            account.key = xml_account.findtext("Key")
            result[serial_number] = account
        # There is always a TuneIn account, but it is handled separately
        #  by Sonos, and does not appear in the xml account data. We
        # need to add it ourselves.
        tunein = Account()
        tunein.service_type = "65031"  # Is this always the case?
        tunein.deleted = False
        tunein.username = ""
        tunein.metadata = ""
        tunein.nickname = ""
        tunein.oa_device_id = ""
        tunein.key = ""
        tunein.serial_number = "0"
        result["0"] = tunein

        return result

    @classmethod
    def get_accounts_for_service(cls, service_type):
        """Get a list of accounts for a given music service.

        Args:
            service_type (str): The service_type to use.

        Returns:
            list: A list of `Account` instances.
        """
        return [
            a for a in cls.get_accounts().values() if a.service_type == service_type
        ]
