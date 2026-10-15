"""Allow RiffLab to start if Windows rejects bundled QtAwesome fonts.

The native Windows font loader can fail on GitHub runners or user machines.
Keep the UI usable (without font icons) rather than aborting Window().
"""
import sys
import qtawesome as _qta
from PySide6.QtGui import QIcon

_original_icon = _qta.icon
_warned = False


def _safe_icon(*args, **kwargs):
    global _warned
    try:
        return _original_icon(*args, **kwargs)
    except _qta.iconic_font.FontError as exc:
        if not _warned:
            print('RiffLab: QtAwesome font unavailable; using blank icon fallback: ' + str(exc), file=sys.stderr, flush=True)
            _warned = True
        return QIcon()


_qta.icon = _safe_icon
