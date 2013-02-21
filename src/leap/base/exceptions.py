"""
Exception attributes and their meaning/uses
-------------------------------------------

* critical:    if True, will abort execution prematurely,
               after attempting any cleaning
               action.

* failfirst:   breaks any error_check loop that is examining
               the error queue.

* message:     the message that will be used in the __repr__ of the exception.

* usermessage: the message that will be passed to user in ErrorDialogs
               in Qt-land.
"""


class LeapException(Exception):
    """
    base LeapClient exception
    sets some parameters that we will check
    during error checking routines
    """

    critical = False
    failfirst = False
    warning = False


class CriticalError(LeapException):
    """
    we cannot do anything about it
    """
    critical = True
    failfirst = True