try:
    import sip
    sip.setapi('QString', 2)
    sip.setapi('QVariant', 2)
except ValueError:
    pass

import intro_page
import connecting_page
import last_page
import login_page
import mixins
import providerinfo_page
import providerselect_page
import providersetup_page
import register_page

__all__ = [
    'intro_page',
    'connecting_page',
    'last_page',
    'login_page',
    'mixins',
    'providerinfo_page',
    'providerselect_page',
    'providersetup_page',
    'register_page',
    ]  # ,'wizard']
