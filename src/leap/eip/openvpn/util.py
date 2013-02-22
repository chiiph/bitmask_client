import platform
import logging
import os

from leap.base.util.permcheck import (is_pkexec_in_system,
                                      is_auth_agent_running)
from leap.base.util.file import which
from leap.eip.config import (EIPConfig,
                             EIPServiceConfig,
                             get_eip_gateway,
                             get_cipher_options)
from leap.base.config import util
from leap.eip import specs as eipspecs

_platform = platform.system()

LINUX_UP_DOWN_SCRIPT = "/etc/leap/resolv-update"
OPENVPN_DOWN_ROOT = "/usr/lib/openvpn/openvpn-down-root.so"

logger = logging.getLogger(name=__name__)

def has_updown_scripts():
    """
    checks the existence of the up/down scripts
    """
    # XXX should check permissions too
    is_file = os.path.isfile(LINUX_UP_DOWN_SCRIPT)
    if not is_file:
        logger.warning(
            "Could not find up/down scripts at %s! "
            "Risk of DNS Leaks!!!")
    return is_file


def build_ovpn_options(daemon=False, socket_path=None, **kwargs):
    """
    build a list of options
    to be passed in the
    openvpn invocation
    @rtype: list
    @rparam: options
    """
    # XXX review which of the
    # options we don't need.

    # TODO pass also the config file,
    # since we will need to take some
    # things from there if present.

    provider = kwargs.pop('provider', None)
    eipconfig = EIPConfig(domain=provider)
    eipconfig.load()
    eipserviceconfig = EIPServiceConfig(domain=provider)
    eipserviceconfig.load()

    # get user/group name
    # also from config.
    user = util.get_username()
    group = util.get_groupname()

    opts = []

    opts.append('--client')

    opts.append('--dev')
    # XXX same in win?
    opts.append('tun')
    opts.append('--persist-tun')
    opts.append('--persist-key')

    verbosity = kwargs.get('ovpn_verbosity', None)
    if verbosity and 1 <= verbosity <= 6:
        opts.append('--verb')
        opts.append("%s" % verbosity)

    # remote ##############################
    # (server, port, protocol)

    opts.append('--remote')

    gw = get_eip_gateway(eipconfig=eipconfig,
                         eipserviceconfig=eipserviceconfig)
    logger.debug('setting eip gateway to %s', gw)
    opts.append(str(gw))

    # get port/protocol from eipservice too
    opts.append('1194')
    #opts.append('80')
    opts.append('udp')

    opts.append('--tls-client')
    opts.append('--remote-cert-tls')
    opts.append('server')

    # get ciphers #######################

    ciphers = get_cipher_options(
        eipserviceconfig=eipserviceconfig)
    for cipheropt in ciphers:
        opts.append(str(cipheropt))

    # set user and group
    opts.append('--user')
    opts.append('%s' % user)
    opts.append('--group')
    opts.append('%s' % group)

    opts.append('--management-client-user')
    opts.append('%s' % user)
    opts.append('--management-signal')

    # set default options for management
    # interface. unix sockets or telnet interface for win.
    # XXX take them from the config object.

    if _platform == "Windows":
        opts.append('--management')
        opts.append('localhost')
        # XXX which is a good choice?
        opts.append('7777')

    if _platform in ("Linux", "Darwin"):
        opts.append('--management')

        if socket_path is None:
            socket_path = get_socket_path()
        opts.append(socket_path)
        opts.append('unix')

        opts.append('--script-security')
        opts.append('2')

    if _platform == "Linux":
        if has_updown_scripts():
            opts.append("--up")
            opts.append(LINUX_UP_DOWN_SCRIPT)
            opts.append("--down")
            opts.append(LINUX_UP_DOWN_SCRIPT)
            opts.append("--plugin")
            opts.append(OPENVPN_DOWN_ROOT)
            opts.append("'script_type=down %s'" % LINUX_UP_DOWN_SCRIPT)

    # certs
    client_cert_path = eipspecs.client_cert_path(provider)
    ca_cert_path = eipspecs.provider_ca_path(provider)

    # XXX FIX paths for MAC
    opts.append('--cert')
    opts.append(client_cert_path)
    opts.append('--key')
    opts.append(client_cert_path)
    opts.append('--ca')
    opts.append(ca_cert_path)

    # we cannot run in daemon mode
    # with the current subp setting.
    # see: https://leap.se/code/issues/383
    #if daemon is True:
        #opts.append('--daemon')

    logger.debug('vpn options: %s', ' '.join(opts))
    return opts


def build_ovpn_command(debug=False, do_pkexec_check=True, vpnbin=None,
                       socket_path=None, **kwargs):
    """
    build a string with the
    complete openvpn invocation

    @rtype [string, [list of strings]]
    @rparam: a list containing the command string
        and a list of options.
    """
    command = []
    use_pkexec = True
    ovpn = None

    # XXX get use_pkexec from config instead.

    if _platform == "Linux" and use_pkexec and do_pkexec_check:

        # check for both pkexec
        # AND a suitable authentication
        # agent running.
        logger.info('use_pkexec set to True')

        if not is_pkexec_in_system():
            logger.error('no pkexec in system')
            raise EIPNoPkexecAvailable()

        if not is_auth_agent_running():
            logger.warning(
                "no polkit auth agent found. "
                "pkexec will use its own text "
                "based authentication agent. "
                "that's probably a bad idea")
            raise EIPNoPolkitAuthAgentAvailable()

        command.append('pkexec')

    if vpnbin is None:
        if _platform == "Darwin":
            # XXX Should hardcode our installed path
            # /Applications/LEAPClient.app/Contents/Resources/openvpn.leap
            openvpn_bin = "openvpn.leap"
        else:
            openvpn_bin = "openvpn"
        #XXX hardcode for darwin
        ovpn = which(openvpn_bin)
    else:
        ovpn = vpnbin
    if ovpn:
        vpn_command = ovpn
    else:
        vpn_command = "openvpn"
    command.append(vpn_command)
    daemon_mode = not debug

    for opt in build_ovpn_options(daemon=daemon_mode, socket_path=socket_path,
                                  **kwargs):
        command.append(opt)

    # XXX check len and raise proper error

    if _platform == "Darwin":
        OSX_ASADMIN = 'do shell script "%s" with administrator privileges'
        # XXX fix workaround for Nones
        _command = [x if x else " " for x in command]
        # XXX debugging!
        # XXX get openvpn log path from debug flags
        _command.append('--log')
        _command.append('/tmp/leap_openvpn.log')
        return ["osascript", ["-e", OSX_ASADMIN % ' '.join(_command)]]
    else:
        return [command[0], command[1:]]
