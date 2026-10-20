"""Qt Quick 3D instance data for the Nucleus particle sphere.

Imported only by the shell when Qt Quick 3D is available. Each instance packs
its sphere target as the translation, its globe target and seed as custom
data, and (spark, ocean, 0, brightness) as colour; the QML shader does all
per-frame motion and morphing on the GPU.
"""

from __future__ import annotations

import struct

from PySide6.QtCore import Property, QByteArray, Signal
from PySide6.QtQml import QmlElement
from PySide6.QtQuick3D import QQuick3DInstancing

from .nucleus import build_particles, load_earth_points

QML_IMPORT_NAME = "ApvisNucleus"
QML_IMPORT_MAJOR_VERSION = 1

_EARTH_CACHE: list[tuple[float, float]] | None = None


def _earth() -> list[tuple[float, float]]:
    global _EARTH_CACHE
    if _EARTH_CACHE is None:
        try:
            _EARTH_CACHE = load_earth_points()
        except (OSError, ValueError):
            _EARTH_CACHE = []
    return _EARTH_CACHE


def instance_buffer(count: int) -> bytes:
    """Pack ``count`` particles as Qt Quick 3D instance table entries (20 floats each)."""
    data = bytearray()
    for p in build_particles(count, _earth()):
        sx, sy, sz = p.sphere
        gx, gy, gz = p.globe
        data += struct.pack(
            "20f",
            1, 0, 0, sx,
            0, 1, 0, sy,
            0, 0, 1, sz,
            1.0 if p.spark else 0.0, 1.0 if p.ocean else 0.0, 0.0, p.brightness,
            gx, gy, gz, p.seed,
        )
    return bytes(data)


@QmlElement
class NucleusInstancing(QQuick3DInstancing):
    countChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._count = 8000
        self._buffer: bytes | None = None
        self.setInstanceCountOverride(self._count)

    def _get_count(self) -> int:
        return self._count

    def _set_count(self, value: int) -> None:
        value = max(1, int(value))
        if value != self._count:
            self._count = value
            self._buffer = None
            self.setInstanceCountOverride(value)
            self.countChanged.emit()
            self.markDirty()

    count = Property(int, _get_count, _set_count, notify=countChanged)

    def getInstanceBuffer(self, *_args):  # PySide expects (buffer, count)
        if self._buffer is None:
            self._buffer = instance_buffer(self._count)
        return QByteArray(self._buffer), self._count
