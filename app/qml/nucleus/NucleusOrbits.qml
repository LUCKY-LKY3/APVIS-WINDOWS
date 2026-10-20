import QtQuick
import "../theme"

// Three small lights orbiting the sphere on tilted paths, dimmer while they
// pass behind it. Tiny cached textures moved per frame. Decorative only.
Item {
    id: orbits
    property real time: 0
    readonly property real radius: Math.min(width, height) / 2
    Repeater {
        model: [[0.84, 0.30, 24, 0.55, 0.0], [0.78, 0.22, -38, -0.42, 2.1], [0.90, 0.16, 70, 0.33, 4.0]]
        delegate: Item {
            id: sat
            required property var modelData
            readonly property real a: orbits.time * modelData[3] + modelData[4]
            readonly property real tilt: modelData[2] * Math.PI / 180
            readonly property real ex: Math.cos(a) * orbits.radius * modelData[0]
            readonly property real ey: Math.sin(a) * orbits.radius * modelData[0] * modelData[1]
            readonly property bool front: Math.sin(a) > 0
            x: orbits.width / 2 + ex * Math.cos(tilt) - ey * Math.sin(tilt) - width / 2
            y: orbits.height / 2 + ex * Math.sin(tilt) + ey * Math.cos(tilt) - height / 2
            width: 26; height: 26
            opacity: front ? 1 : 0.28
            scale: front ? 1 : 0.7
            Canvas {
                anchors.fill: parent
                Component.onCompleted: requestPaint()
                onPaint: {
                    const c = getContext("2d"), r = width / 2
                    c.reset()
                    const g = c.createRadialGradient(r, r, 0, r, r, r)
                    const col = Theme.accent
                    g.addColorStop(0, Theme.css(Theme.sheenBase, 0.95))
                    g.addColorStop(0.18, "rgba(" + Math.round(col.r * 255) + "," + Math.round(col.g * 255) + "," + Math.round(col.b * 255) + ",0.7)")
                    g.addColorStop(1, "rgba(" + Math.round(col.r * 255) + "," + Math.round(col.g * 255) + "," + Math.round(col.b * 255) + ",0)")
                    c.fillStyle = g; c.fillRect(0, 0, width, height)
                }
            }
        }
    }
}
