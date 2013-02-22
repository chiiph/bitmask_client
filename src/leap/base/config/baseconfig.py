"""
Configuration Base Class
"""
import json
import logging
import time
import os
import requests

from dateutil import parser as dateparser

from leap.base.util.file import mkdir_p
from leap.base.util.translations import translate
from leap.base.config.pluggableconfig import PluggableConfig
from leap.base.config.util import get_config_file

logger = logging.getLogger(name=__name__)


class ImproperlyConfigured(Exception):
    pass


class LeapBadConfigFetchedError(Warning):
    message = "provider sent a malformed json file"
    usermessage = translate(
        "EIPErrors",
        "an error occurred during configuratio of leap services")


class BaseLeapConfig(object):
    slug = None

    # XXX we have to enforce that every derived class
    # has a slug (via interface)
    # get property getter that raises NI..

    def save(self):
        raise NotImplementedError("abstract base class")

    def load(self):
        raise NotImplementedError("abstract base class")

    def get_config(self, *kwargs):
        raise NotImplementedError("abstract base class")

    @property
    def config(self):
        return self.get_config()

    def get_value(self, *kwargs):
        raise NotImplementedError("abstract base class")


class MetaConfigWithSpec(type):
    """
    metaclass for JSONLeapConfig classes.
    It creates a configuration spec out of
    the `spec` dictionary. The `properties` attribute
    of the spec dict is turn into the `schema` attribute
    of the new class (which will be used to validate against).
    """
    # XXX in the near future, this is the
    # place where we want to enforce
    # singletons, read-only and similar stuff.

    def __new__(meta, classname, bases, classDict):
        schema_obj = classDict.get('spec', None)

        # not quite happy with this workaround.
        # I want to raise if missing spec dict, but only
        # for grand-children of this metaclass.
        # maybe should use abc module for this.
        abcderived = ("JSONLeapConfig",)
        if schema_obj is None and classname not in abcderived:
            raise ImproperlyConfigured(
                "missing spec dict on your derived class (%s)" % classname)

        # we create a configuration spec attribute
        # from the spec dict
        config_class = type(
            classname + "Spec",
            (PluggableConfig, object),
            {'options': schema_obj})
        classDict['spec'] = config_class

        return type.__new__(meta, classname, bases, classDict)

##########################################################
# some hacking still in progress:

# Configs have:

# - a slug (from where a filename/folder is derived)
# - a spec (for validation and defaults).
#   this spec is conformant to the json-schema.
#   basically a dict that will be used
#   for type casting and validation, and defaults settings.

# all config objects, since they are derived from  BaseConfig, implement basic
# useful methods:
# - save
# - load

##########################################################


class JSONLeapConfig(BaseLeapConfig):

    __metaclass__ = MetaConfigWithSpec

    def __init__(self, *args, **kwargs):
        # sanity check
        try:
            assert self.slug is not None
        except AssertionError:
            raise ImproperlyConfigured(
                "missing slug on JSONLeapConfig"
                " derived class")
        try:
            assert self.spec is not None
        except AssertionError:
            raise ImproperlyConfigured(
                "missing spec on JSONLeapConfig"
                " derived class")
        assert issubclass(self.spec, PluggableConfig)

        self.domain = kwargs.pop('domain', None)
        self._config = self.spec(format="json")
        self._config.load()
        self.fetcher = kwargs.pop('fetcher', requests)

    # mandatory baseconfig interface

    def save(self, to=None, force=False):
        """
        force param will skip the dirty check.
        :type force: bool
        """
        # XXX this force=True does not feel to right
        # but still have to look for a better way
        # of dealing with dirtiness and the
        # trick of loading remote config only
        # when newer.

        if force:
            do_save = True
        else:
            do_save = self._config.is_dirty()

        if do_save:
            if to is None:
                to = self.filename
            folder, filename = os.path.split(to)
            if folder and not os.path.isdir(folder):
                mkdir_p(folder)
            self._config.serialize(to)
            return True

        else:
            return False

    def load(self, fromfile=None, from_uri=None, fetcher=None,
             force_download=False, verify=True):

        if from_uri is not None:
            fetched = self.fetch(
                from_uri,
                fetcher=fetcher,
                verify=verify,
                force_dl=force_download)
            if fetched:
                return
        if fromfile is None:
            fromfile = self.filename
        if os.path.isfile(fromfile):
            self._config.load(fromfile=fromfile)
        else:
            logger.error('tried to load config from non-existent path')
            logger.error('Not Found: %s', fromfile)

    def fetch(self, uri, fetcher=None, verify=True, force_dl=False):
        if not fetcher:
            fetcher = self.fetcher

        logger.debug('uri: %s (verify: %s)' % (uri, verify))

        rargs = (uri, )
        rkwargs = {'verify': verify}
        headers = {}

        curmtime = self.get_mtime() if not force_dl else None
        if curmtime:
            logger.debug('requesting with if-modified-since %s' % curmtime)
            headers['if-modified-since'] = curmtime
            rkwargs['headers'] = headers

        #request = fetcher.get(uri, verify=verify)
        request = fetcher.get(*rargs, **rkwargs)
        request.raise_for_status()

        if request.status_code == 304:
            logger.debug('...304 Not Changed')
            # On this point, we have to assume that
            # we HAD the filename. If that filename is corruct,
            # we should enforce a force_download in the load
            # method above.
            self._config.load(fromfile=self.filename)
            return True

        if request.json:
            mtime = None
            last_modified = request.headers.get('last-modified', None)
            if last_modified:
                _mtime = dateparser.parse(last_modified)
                mtime = int(_mtime.strftime("%s"))
            if callable(request.json):
                _json = request.json()
            else:
                # back-compat
                _json = request.json
            self._config.load(json.dumps(_json), mtime=mtime)
            self._config.set_dirty()
        else:
            # not request.json
            # might be server did not announce content properly,
            # let's try deserializing all the same.
            try:
                self._config.load(request.content)
                self._config.set_dirty()
            except ValueError:
                raise LeapBadConfigFetchedError()

        return True

    def get_mtime(self):
        try:
            _mtime = os.stat(self.filename)[8]
            mtime = time.strftime("%c GMT", time.gmtime(_mtime))
            return mtime
        except OSError:
            return None

    def get_config(self):
        return self._config.config

    # public methods

    def get_filename(self):
        return self._slug_to_filename()

    @property
    def filename(self):
        return self.get_filename()

    def validate(self, data):
        logger.debug('validating schema')
        self._config.validate(data)
        return True

    # private

    def _slug_to_filename(self):
        # is this going to work in winland if slug is "foo/bar" ?
        folder, filename = os.path.split(self.slug)
        config_file = get_config_file(filename, folder)
        return config_file

    def exists(self):
        return os.path.isfile(self.filename)