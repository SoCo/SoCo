# -*- coding: utf-8 -*-

"""Accounts for Third Party music services."""

from __future__ import unicode_literals

import weakref
import logging
log = logging.getLogger(__name__)  # pylint: disable=C0103

import requests

from soco.core import SoCo
from soco.xml import XML


# pylint: disable=too-many-instance-attributes
class Account(object):

    """An account for a Music Service.

    Each service may have more than one account: see
    http://www.sonos.com/en-gb/software/release/5-2

    """

    _all_accounts = weakref.WeakValueDictionary()

    def __init__(self):
        """Constructor.

        Args:
            service_type (str): A unique identifier for the music service to
                which this account relates, eg '2311' for Spotify.
            serial_number: (str): A unique identifier for this account
            nickname (str): The account's nickname
            deleted (bool): True if this account has been deleted
            username (str): The username used for logging into the music
                service
            metadata (str): Metadata for the account
            oa_device_id (str): Used for OpenAuth id for some services
            key (str): Used for OpenAuthid for some services

        """

        super(Account, self).__init__()
        self.service_type = ''
        self.serial_number = ''
        self.nickname = ''
        self.deleted = False
        self.username = ''
        self.metadata = ''
        self.oa_device_id = ''
        self.key = ''

    def __repr__(self):
        return "<{0} '{1}:{2}:{3}' at {4}>".format(
            self.__class__.__name__,
            self.serial_number,
            self.service_type,
            self.nickname,
            hex(id(self))
        )

    def __str__(self):
        return self.__repr__()

    @staticmethod
    def _get_account_xml(soco):
        """Fetch the account data from a Sonos device.

        Args:
            soco (SoCo): a SoCo instance to query. If soco is none, a
                random device will be used.

        Returns:
            (str): a byte string containing the account data xml

        """
        # It is likely that the same information is available over UPnP as well
        # via a call to
        # systemProperties.GetStringX([('VariableName','R_SvcAccounts')]))
        # This returns an encrypted string, and, so far, we cannot decrypt it
        device = soco or SoCo.any_soco()
        log.debug("Fetching account data from %s", device)
        settings_url = "http://{0}:1400/status/accounts".format(
            device.ip_address)
        result = requests.get(settings_url).content
        log.debug("Account data: %s", result)
        return result

    @classmethod
    def get_accounts(cls, soco=None):
        """Get a dict containing all accounts known to the Sonos system.

        Args:
            soco (SoCo, optional): a SoCo instance to query. If None, a random
            instance is used. Defaults to None

        Returns:
            dict: A dict containing account instances. Each key is the
            account's serial number, and each value is the related Account
            instance. Accounts which have been marked as deleted are excluded.

        Note:
            Although an Account for TuneIn is always present, it is handled
            specially by Sonos, and will not appear in the returned dict. Any
            existing Account instance will have its attributes updated to
            those currently stored on the Sonos system.

        """

        root = XML.fromstring(cls._get_account_xml(soco))
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

        # pylint: disable=protected-access

        accounts = root.findall('.//Account')
        result = {}
        for account in accounts:
            serial_number = account.get('SerialNum')
            is_deleted = True if account.get('Deleted') == '1' else False
            if cls._all_accounts.get(serial_number):
                if is_deleted:
                    del cls._all_accounts[serial_number]
                    continue
                else:
                    acct = cls._all_accounts.get(serial_number)
            else:
                if is_deleted:
                    continue
                acct = Account()
                acct.serial_number = serial_number
                cls._all_accounts[serial_number] = acct

            acct.service_type = account.get('Type')
            acct.deleted = is_deleted
            acct.username = account.findtext('UN')
            # Not sure what 'MD' stands for.  Metadata?
            acct.metadata = account.findtext('MD')
            acct.nickname = account.findtext('NN')
            acct.oa_device_id = account.findtext('OADevID')
            acct.key = account.findtext('Key')

            result[serial_number] = acct
        return result

    @classmethod
    def get_accounts_for_service(cls, service_type):
        """Get a list of accounts for a given music service.

        Args:
            service_type (str): The service_type to use

        Returns:
            (list): A list of MusicAccount instances

        """
        return [
            a for a in cls.get_accounts().values()
            if a.service_type == service_type
        ]
