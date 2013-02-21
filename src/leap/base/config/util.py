import os
import re
import socket
import grp

from xdg import BaseDirectory

from leap.base import constants

def get_config_dir():
    """
    get the base dir for all leap config
    @rparam: config path
    @rtype: string
    """
    home = os.path.expanduser("~")
    if re.findall("leap_tests-[_a-zA-Z0-9]{6}", home):
        # we're inside a test! :)
        return os.path.join(home, ".config/leap")
    else:
        # XXX dirspec is cross-platform,
        # we should borrow some of those
        # routines for osx/win and wrap this call.
        return os.path.join(BaseDirectory.xdg_config_home,
                        'leap')


def get_config_file(filename, folder=None):
    """
    concatenates the given filename
    with leap config dir.
    @param filename: name of the file
    @type filename: string
    @rparam: full path to config file
    """
    path = []
    path.append(get_config_dir())
    if folder is not None:
        path.append(folder)
    path.append(filename)
    return os.path.join(*path)


def get_default_provider_path():
    default_subpath = os.path.join("providers",
                                   constants.DEFAULT_PROVIDER)
    default_provider_path = get_config_file(
        '',
        folder=default_subpath)
    return default_provider_path


def get_provider_path(domain):
    # XXX if not domain, return get_default_provider_path
    default_subpath = os.path.join("providers", domain)
    provider_path = get_config_file(
        '',
        folder=default_subpath)
    return provider_path


def validate_ip(ip_str):
    """
    raises exception if the ip_str is
    not a valid representation of an ip
    """
    socket.inet_aton(ip_str)


def get_username():
    try:
        return os.getlogin()
    except OSError as e:
        import pwd
        return pwd.getpwuid(os.getuid())[0]


def get_groupname():
    gid = os.getgroups()[-1]
    return grp.getgrgid(gid).gr_name
