try:
    import sip
    sip.setapi('QString', 2)
    sip.setapi('QVariant', 2)
except ValueError:
    pass

import wizards.firstrun
import wizards.firstrun.wizard

__all__ = ['firstrun', 'firstrun.wizard']
