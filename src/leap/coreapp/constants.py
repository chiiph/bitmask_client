import time

# This timer used for polling vpn manager state.

# XXX what is an optimum polling interval?
# too little will be overkill, too much will
# miss transition states.
TIMER_MILLISECONDS = 250.0

APP_LOGO = ':/images/leap-color-small.png'

# bare is the username portion of a JID
# full includes the "at" and some extra chars
# that can be allowed for fqdn

BARE_USERNAME_REGEX = r"^[A-Za-z\d_]+$"
FULL_USERNAME_REGEX = r"^[A-Za-z\d_@.-]+$"

GUI_PAUSE_FOR_USER_SECONDS = 1
pause_for_user = lambda: time.sleep(GUI_PAUSE_FOR_USER_SECONDS)

DELAY_MSECS = 50