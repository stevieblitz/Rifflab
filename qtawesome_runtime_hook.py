"""RiffLab Windows workaround: avoid native crashes while painting QtAwesome font icons.

Windows font loading on the build runner reported empty Font Awesome fonts.
Return an empty QIcon before QtAwesome creates a font-backed icon engine.
Buttons retain their text and all connected actions.
"""
import sys
import qtawesome as _qta
from PySide6.QtGui import QIcon

if sys.platform == 'win32':
    def _safe_icon(*args, **kwargs):
        return QIcon()
    _qta.icon = _safe_icon
    print('RIFFLAB_BOOT: QtAwesome font-backed icons disabled on Windows', file=sys.stderr, flush=True)
