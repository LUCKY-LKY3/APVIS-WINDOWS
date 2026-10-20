import QtQuick
import "../theme"

// Neural Fabric links: a curved light line from each widget to the core. A pulse
// travels along a link only when that widget's real data actually updates
// (DESIGN-LANGUAGE: "Flow = actual information transfer"). Idle links stay dim.
Item {
    id: fabric
    // [{ key, x, y, side: -1 (left of core) | 1 (right), live: bool }]
    property var sockets: []
    property point core: Qt.point(0, 0)
    property real ring: 100

    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
    // Bezier from the widget edge to a point on the core's ring.
    function curve(a) {
        const dy = a.y - core.y, dx = a.x - core.x
        const ang = Math.atan2(dy * 0.8, dx)
        const ex = core.x + Math.cos(ang) * ring, ey = core.y + Math.sin(ang) * ring
        const midx = (a.x + ex) / 2
        return { x0: a.x, y0: a.y, c1x: midx, c1y: a.y, c2x: midx, c2y: ey, x1: ex, y1: ey }
    }
    function at(c, t) {
        const u = 1 - t
        return Qt.point(u*u*u*c.x0 + 3*u*u*t*c.c1x + 3*u*t*t*c.c2x + t*t*t*c.x1,
                        u*u*u*c.y0 + 3*u*u*t*c.c1y + 3*u*t*t*c.c2y + t*t*t*c.y1)
    }
    onSocketsChanged: lines.requestPaint()
    onCoreChanged: lines.requestPaint()
    onRingChanged: lines.requestPaint()

    Canvas {
        id: lines
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onPaint: {
            const c = getContext("2d")
            c.reset(); c.clearRect(0, 0, width, height)
            c.globalCompositeOperation = "lighter"
            for (const a of fabric.sockets) {
                const k = fabric.curve(a), live = a.live
                for (let pass = 0; pass < 3; ++pass) {
                    c.lineWidth = [6, 2.5, 1][pass]
                    c.strokeStyle = fabric.rgba(Theme.accent, (live ? [0.05, 0.12, 0.55] : [0.02, 0.05, 0.22])[pass])
                    c.beginPath(); c.moveTo(k.x0, k.y0); c.bezierCurveTo(k.c1x, k.c1y, k.c2x, k.c2y, k.x1, k.y1); c.stroke()
                }
                // Socket at the widget, tick at the ring.
                c.fillStyle = fabric.rgba(live ? Theme.text : Theme.muted, live ? 0.95 : 0.5)
                c.beginPath(); c.arc(k.x0, k.y0, 3, 0, Math.PI * 2); c.fill()
                c.strokeStyle = fabric.rgba(Theme.accent, live ? 0.8 : 0.35); c.lineWidth = 1
                c.beginPath(); c.arc(k.x0, k.y0, 6.5, 0, Math.PI * 2); c.stroke()
                c.beginPath(); c.arc(k.x1, k.y1, 2.2, 0, Math.PI * 2); c.fill()
            }
        }
    }

    // Pulses: one travelling light per link, fired by pulse(key).
    function pulse(key) {
        for (let i = 0; i < pulses.count; ++i) {
            const p = pulses.itemAt(i)
            if (p && p.key === key) p.fire()
        }
    }
    Repeater {
        id: pulses
        model: fabric.sockets
        delegate: Item {
            id: pulseItem
            required property var modelData
            readonly property string key: modelData.key
            property real t: 0
            readonly property var k: fabric.curve(modelData)
            readonly property point pos: fabric.at(k, t)
            visible: run.running
            x: pos.x; y: pos.y
            function fire() { run.restart() }
            NumberAnimation { id: run; target: pulseItem; property: "t"; from: 0; to: 1; duration: 1100; easing.type: Easing.InOutQuad }
            Rectangle { anchors.centerIn: parent; width: 18; height: 18; radius: 9; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.22) }
            Rectangle { anchors.centerIn: parent; width: 8; height: 8; radius: 4; color: Theme.accent }
            Rectangle { anchors.centerIn: parent; width: 3.5; height: 3.5; radius: 1.75; color: Theme.text }
        }
    }
}
