# -*- coding: utf-8 -*-
# providerbootstrapper.py
# Copyright (C) 2013 LEAP
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Provider bootstrapping
"""
import logging
import socket
import os

import requests

from PySide import QtCore
from twisted.internet import threads

from leap.common.certs import get_digest
from leap.common.files import check_and_fix_urw_only, get_mtime, mkdir_p
from leap.common.check import leap_assert, leap_assert_type
from leap.config.providerconfig import ProviderConfig
from leap.util.request_helpers import get_content
from leap.services.abstractbootstrapper import AbstractBootstrapper

logger = logging.getLogger(__name__)


class ProviderBootstrapper(AbstractBootstrapper):
    """
    Given a provider URL performs a series of checks and emits signals
    after they are passed.
    If a check fails, the subsequent checks are not executed
    """

    # All dicts returned are of the form
    # {"passed": bool, "error": str}
    name_resolution = QtCore.Signal(dict)
    https_connection = QtCore.Signal(dict)
    download_provider_info = QtCore.Signal(dict)

    download_ca_cert = QtCore.Signal(dict)
    check_ca_fingerprint = QtCore.Signal(dict)
    check_api_certificate = QtCore.Signal(dict)

    def __init__(self, bypass_checks=False):
        """
        Constructor for provider bootstrapper object

        :param bypass_checks: Set to true if the app should bypass
        first round of checks for CA certificates at bootstrap
        :type bypass_checks: bool
        """
        AbstractBootstrapper.__init__(self, bypass_checks)

        self._domain = None
        self._provider_config = None
        self._download_if_needed = False

    def _check_name_resolution(self):
        """
        Checks that the name resolution for the provider name works
        """
        leap_assert(self._domain, "Cannot check DNS without a domain")

        logger.debug("Checking name resolution for %s" % (self._domain))

        # We don't skip this check, since it's basic for the whole
        # system to work
        socket.gethostbyname(self._domain)

    def _check_https(self, *args):
        """
        Checks that https is working and that the provided certificate
        checks out
        """

        leap_assert(self._domain, "Cannot check HTTPS without a domain")

        logger.debug("Checking https for %s" % (self._domain))

        # We don't skip this check, since it's basic for the whole
        # system to work

        try:
            res = self._session.get("https://%s" % (self._domain,),
                                    verify=not self._bypass_checks)
            res.raise_for_status()
        except requests.exceptions.SSLError:
            self._err_msg = self.tr("Provider certificate could "
                                    "not verify")
            raise
        except Exception:
            self._err_msg = self.tr("Provider does not support HTTPS")
            raise

    def _download_provider_info(self, *args):
        """
        Downloads the provider.json defition
        """
        leap_assert(self._domain,
                    "Cannot download provider info without a domain")

        logger.debug("Downloading provider info for %s" % (self._domain))

        headers = {}
        mtime = get_mtime(os.path.join(ProviderConfig()
                                       .get_path_prefix(),
                                       "leap",
                                       "providers",
                                       self._domain,
                                       "provider.json"))
        if self._download_if_needed and mtime:
            headers['if-modified-since'] = mtime

        res = self._session.get("https://%s/%s" % (self._domain,
                                                   "provider.json"),
                                headers=headers,
                                verify=not self._bypass_checks)
        res.raise_for_status()

        # Not modified
        if res.status_code == 304:
            logger.debug("Provider definition has not been modified")
        else:
            provider_definition, mtime = get_content(res)

            provider_config = ProviderConfig()
            provider_config.load(data=provider_definition, mtime=mtime)
            provider_config.save(["leap",
                                  "providers",
                                  self._domain,
                                  "provider.json"])

    def run_provider_select_checks(self, domain, download_if_needed=False):
        """
        Populates the check queue.

        :param domain: domain to check
        :type domain: str

        :param download_if_needed: if True, makes the checks do not
                                   overwrite already downloaded data
        :type download_if_needed: bool
        """
        leap_assert(domain and len(domain) > 0, "We need a domain!")

        self._domain = domain
        self._download_if_needed = download_if_needed

        self._signal_to_emit = None
        self._err_msg = None

        d = threads.deferToThread(self._check_name_resolution)
        d.addErrback(self._errback, signal=self.name_resolution)
        d.addCallback(self._gui_notify, signal=self.name_resolution)

        d.addCallback(self._check_https)
        d.addErrback(self._errback, signal=self.https_connection)
        d.addCallback(self._gui_notify, signal=self.https_connection)

        d.addCallback(self._download_provider_info)
        d.addErrback(self._errback, signal=self.download_provider_info)
        d.addCallback(self._gui_notify, signal=self.download_provider_info)
        d.addErrback(self._gui_errback)

    def _should_proceed_cert(self):
        """
        Returns False if the certificate already exists for the given
        provider. True otherwise

        :rtype: bool
        """
        leap_assert(self._provider_config, "We need a provider config!")

        if not self._download_if_needed:
            return True

        return not os.path.exists(self._provider_config
                                  .get_ca_cert_path(about_to_download=True))

    def _download_ca_cert(self, *args):
        """
        Downloads the CA cert that is going to be used for the api URL
        """

        leap_assert(self._provider_config, "Cannot download the ca cert "
                    "without a provider config!")

        logger.debug("Downloading ca cert for %s at %s" %
                     (self._domain, self._provider_config.get_ca_cert_uri()))

        if not self._should_proceed_cert():
            check_and_fix_urw_only(
                self._provider_config
                .get_ca_cert_path(about_to_download=True))

        res = self._session.get(self._provider_config.get_ca_cert_uri(),
                                verify=not self._bypass_checks)
        res.raise_for_status()

        cert_path = self._provider_config.get_ca_cert_path(
            about_to_download=True)
        cert_dir = os.path.dirname(cert_path)
        mkdir_p(cert_dir)
        with open(cert_path, "w") as f:
            f.write(res.content)

        check_and_fix_urw_only(cert_path)

    def _check_ca_fingerprint(self, *args):
        """
        Checks the CA cert fingerprint against the one provided in the
        json definition
        """
        leap_assert(self._provider_config, "Cannot check the ca cert "
                    "without a provider config!")

        logger.debug("Checking ca fingerprint for %s and cert %s" %
                     (self._domain,
                      self._provider_config.get_ca_cert_path()))

        if not self._should_proceed_cert():
            return

        parts = self._provider_config.get_ca_cert_fingerprint().split(":")
        leap_assert(len(parts) == 2, "Wrong fingerprint format")

        method = parts[0].strip()
        fingerprint = parts[1].strip()
        cert_data = None
        with open(self._provider_config.get_ca_cert_path()) as f:
            cert_data = f.read()

        leap_assert(len(cert_data) > 0, "Could not read certificate data")
        digest = get_digest(cert_data, method)
        leap_assert(digest == fingerprint,
                    "Downloaded certificate has a different fingerprint!")

    def _check_api_certificate(self, *args):
        """
        Tries to make an API call with the downloaded cert and checks
        if it validates against it
        """
        leap_assert(self._provider_config, "Cannot check the ca cert "
                    "without a provider config!")

        logger.debug("Checking api certificate for %s and cert %s" %
                     (self._provider_config.get_api_uri(),
                      self._provider_config.get_ca_cert_path()))

        if not self._should_proceed_cert():
            return

        test_uri = "%s/%s/cert" % (self._provider_config.get_api_uri(),
                                   self._provider_config.get_api_version())
        res = self._session.get(test_uri,
                                verify=self._provider_config
                                .get_ca_cert_path())
        res.raise_for_status()

    def run_provider_setup_checks(self,
                                  provider_config,
                                  download_if_needed=False):
        """
        Starts the checks needed for a new provider setup.

        :param provider_config: Provider configuration
        :type provider_config: ProviderConfig

        :param download_if_needed: if True, makes the checks do not
                                   overwrite already downloaded data.
        :type download_if_needed: bool
        """
        leap_assert(provider_config, "We need a provider config!")
        leap_assert_type(provider_config, ProviderConfig)

        self._provider_config = provider_config
        self._download_if_needed = download_if_needed

        self._signal_to_emit = None
        self._err_msg = None

        d = threads.deferToThread(self._download_ca_cert)
        d.addErrback(self._errback, signal=self.download_ca_cert)
        d.addCallback(self._gui_notify, signal=self.download_ca_cert)

        d.addCallback(self._check_ca_fingerprint)
        d.addErrback(self._errback, signal=self.check_ca_fingerprint)
        d.addCallback(self._gui_notify, signal=self.check_ca_fingerprint)

        d.addCallback(self._check_api_certificate)
        d.addErrback(self._errback, signal=self.check_api_certificate)
        d.addCallback(self._gui_notify, signal=self.check_api_certificate)
        d.addErrback(self._gui_errback)
