import logging
import os
import re
import tempfile

from leap import __branding as BRANDING
from leap import certs
from leap.base.config import baseconfig, util
from leap.base.util.misc import null_check
from leap.base.util.file import (mkdir_p, check_and_fix_urw_only)
from leap.base.exceptions import CriticalError, Warning
from leap.base.util.translations import translate
from leap.eip import specs as eipspecs

logger = logging.getLogger(name=__name__)
provider_ca_file = BRANDING.get('provider_ca_file', None)

class EIPNoPolkitAuthAgentAvailable(CriticalError):
    message = "No polkit authentication agent could be found"
    usermessage = translate(
        "EIPErrors",
        "We could not find any authentication "
        "agent in your system.<br/>"
        "Make sure you have "
        "<b>polkit-gnome-authentication-agent-1</b> "
        "running and try again.")


class EIPNoPkexecAvailable(Warning):
    message = "No pkexec binary found"
    usermessage = translate(
        "EIPErrors",
        "We could not find <b>pkexec</b> in your "
        "system.<br/> Do you want to try "
        "<b>setuid workaround</b>? "
        "(<i>DOES NOTHING YET</i>)")
    failfirst = True


class EIPInitNoKeyFileError(CriticalError):
    message = "No vpn keys found in the expected path"
    usermessage = translate(
        "EIPErrors",
        "We could not find your eip certs in the expected path")


class EIPInitBadKeyFilePermError(Warning):
    # I don't know if we should be telling user or not,
    # we try to fix permissions and should only re-raise
    # if permission check failed.
    pass


class EIPConfig(baseconfig.JSONLeapConfig):
    spec = eipspecs.eipconfig_spec

    def _get_slug(self):
        eipjsonpath = util.get_config_file(
            'eip.json')
        return eipjsonpath

    def _set_slug(self, *args, **kwargs):
        raise AttributeError("you cannot set slug")

    slug = property(_get_slug, _set_slug)


class EIPServiceConfig(baseconfig.JSONLeapConfig):
    spec = eipspecs.eipservice_config_spec

    def _get_slug(self):
        domain = getattr(self, 'domain', None)
        if domain:
            path = util.get_provider_path(domain)
        else:
            path = util.get_default_provider_path()
        return util.get_config_file(
            'eip-service.json', folder=path)

    def _set_slug(self):
        raise AttributeError("you cannot set slug")

    slug = property(_get_slug, _set_slug)


def get_socket_path():
    socket_path = os.path.join(
        tempfile.mkdtemp(prefix="leap-tmp"),
        'openvpn.socket')
    #logger.debug('socket path: %s', socket_path)
    return socket_path


def get_eip_gateway(eipconfig=None, eipserviceconfig=None):
    """
    return the first host in eip service config
    that matches the name defined in the eip.json config
    file.
    """
    # XXX eventually we should move to a more clever
    # gateway selection. maybe we could return
    # all gateways that match our cluster.

    null_check(eipconfig, "eipconfig")
    null_check(eipserviceconfig, "eipserviceconfig")
    PLACEHOLDER = "testprovider.example.org"

    conf = eipconfig.config
    eipsconf = eipserviceconfig.config

    primary_gateway = conf.get('primary_gateway', None)
    if not primary_gateway:
        return PLACEHOLDER

    gateways = eipsconf.get('gateways', None)
    if not gateways:
        logger.error('missing gateways in eip service config')
        return PLACEHOLDER

    if len(gateways) > 0:
        for gw in gateways:
            clustername = gw.get('cluster', None)
            if not clustername:
                logger.error('no cluster name')
                return

            if clustername == primary_gateway:
                # XXX at some moment, we must
                # make this a more generic function,
                # and return ports, protocols...
                ipaddress = gw.get('ip_address', None)
                if not ipaddress:
                    logger.error('no ip_address')
                    return
                return ipaddress
    logger.error('could not find primary gateway in provider'
                 'gateway list')


def get_cipher_options(eipserviceconfig=None):
    """
    gathers optional cipher options from eip-service config.
    :param eipserviceconfig: EIPServiceConfig instance
    """
    null_check(eipserviceconfig, 'eipserviceconfig')
    eipsconf = eipserviceconfig.get_config()

    ALLOWED_KEYS = ("auth", "cipher", "tls-cipher")
    CIPHERS_REGEX = re.compile("[A-Z0-9\-]+")
    opts = []
    if 'openvpn_configuration' in eipsconf:
        config = eipserviceconfig.config.get(
            "openvpn_configuration", {})
        for key, value in config.items():
            if key in ALLOWED_KEYS and value is not None:
                sanitized_val = CIPHERS_REGEX.findall(value)
                if len(sanitized_val) != 0:
                    _val = sanitized_val[0]
                    opts.append('--%s' % key)
                    opts.append('%s' % _val)
    return opts

def check_vpn_keys(provider=None):
    """
    performs an existance and permission check
    over the openvpn keys file.
    Currently we're expecting a single file
    per provider, containing the CA cert,
    the provider key, and our client certificate
    """
    assert provider is not None
    provider_ca = eipspecs.provider_ca_path(provider)
    client_cert = eipspecs.client_cert_path(provider)

    logger.debug('provider ca = %s', provider_ca)
    logger.debug('client cert = %s', client_cert)

    # if no keys, raise error.
    # it's catched by the ui and signal user.

    if not os.path.isfile(provider_ca):
        # not there. let's try to copy.
        folder, filename = os.path.split(provider_ca)
        if not os.path.isdir(folder):
            mkdir_p(folder)
        if provider_ca_file:
            cacert = certs.where(provider_ca_file)
        with open(provider_ca, 'w') as pca:
            with open(cacert, 'r') as cac:
                pca.write(cac.read())

    if not os.path.isfile(provider_ca):
        logger.error('key file %s not found. aborting.',
                     provider_ca)
        raise EIPInitNoKeyFileError()

    if not os.path.isfile(client_cert):
        logger.error('key file %s not found. aborting.',
                     client_cert)
        raise EIPInitNoKeyFileError()

    for keyfile in (provider_ca, client_cert):
        # bad perms? try to fix them
        try:
            check_and_fix_urw_only(keyfile)
        except OSError:
            raise EIPInitBadKeyFilePermError()
