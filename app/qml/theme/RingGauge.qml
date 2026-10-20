import QtQuick

// Circular HUD gauge: tick ring, background track, glowing value arc, big
// monospace value. `value` is a real percentage or null (shown as "—").
Item {
    id: gauge
    property var value: null
    property string label: ""
    property string sub: ""
    implicitWidth: 96
    implicitHeight: 96
    onValueChanged: arc.requestPaint()

    Canvas {
        id: arc
        anchors.fill: parent
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()
        function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
        onPaint: {
            const c = getContext("2d"), w = width, h = height, cx = w / 2, cy = h / 2, r = Math.min(w, h) / 2 - 6
            c.reset(); c.clearRect(0, 0, w, h)
            const start = Math.PI * 0.75, span = Math.PI * 1.5
            // ticks
            for (let i = 0; i <= 30; ++i) {
                const a = start + span * i / 30, major = i % 5 === 0
                c.strokeStyle = rgba(major ? Theme.text : Theme.accent, major ? 0.55 : 0.25); c.lineWidth = major ? 1.2 : 0.7
                c.beginPath(); c.moveTo(cx + Math.cos(a) * (r + 4), cy + Math.sin(a) * (r + 4))
                c.lineTo(cx + Math.cos(a) * (r + (major ? 0 : 2)), cy + Math.sin(a) * (r + (major ? 0 : 2))); c.stroke()
            }
            // track
            c.strokeStyle = rgba(Theme.line, 1); c.lineWidth = 4
            c.beginPath(); c.arc(cx, cy, r - 6, start, start + span); c.stroke()
            if (gauge.value === null || gauge.value === undefined) return
            const f = Math.max(0, Math.min(1, gauge.value / 100)), col = f >= 0.9 ? Theme.attention : Theme.accent
            c.strokeStyle = rgba(col, 0.22); c.lineWidth = 10
            c.beginPath(); c.arc(cx, cy, r - 6, start, start + span * f); c.stroke()
            c.strokeStyle = rgba(col, 1); c.lineWidth = 3.5
            c.beginPath(); c.arc(cx, cy, r - 6, start, start + span * f); c.stroke()
            const ea = start + span * f
            c.fillStyle = rgba(Theme.text, 1); c.beginPath(); c.arc(cx + Math.cos(ea) * (r - 6), cy + Math.sin(ea) * (r - 6), 2.6, 0, Math.PI * 2); c.fill()
        }
    }
    Column {
        anchors.centerIn: parent
        spacing: 0
        Text { anchors.horizontalCenter: parent.horizontalCenter
               text: gauge.value === null || gauge.value === undefined ? "—" : Math.round(gauge.value) + "%"
               color: Theme.text; font.family: Theme.monoFont; font.pixelSize: Math.max(12, gauge.width * 0.19) }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: gauge.label
               color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: Math.max(8, gauge.width * 0.09); font.letterSpacing: Theme.caps ? 1.5 : 0.3 }
    }
    Text { visible: gauge.sub.length > 0; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom
           text: gauge.sub; color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 9 }
    Accessible.role: Accessible.Indicator
    Accessible.name: label + ": " + (value === null || value === undefined ? "not measured" : Math.round(value) + " percent")
}
