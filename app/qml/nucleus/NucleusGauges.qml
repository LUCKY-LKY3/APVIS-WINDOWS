import QtQuick
import "../theme"

// Live readouts built into the core ring: CPU load (left arc), memory in use
// (right arc) and the local-AI link (bottom). Real values from the shell's
// system sampler; an unknown value draws an empty arc and "—". Repaints only
// when a value changes.
Canvas {
    id: gauges
    property real cpu: -1         // percent, -1 = not measured
    property real memory: -1
    property bool aiOnline: false
    property string aiWord: ""
    antialiasing: true
    onCpuChanged: requestPaint()
    onMemoryChanged: requestPaint()
    onAiOnlineChanged: requestPaint()
    onAiWordChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    Component.onCompleted: requestPaint()
    Connections { target: Theme; function onAccentNameChanged() { gauges.requestPaint() } }
    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }

    onPaint: {
        const c = getContext("2d"), cx = width / 2, cy = height / 2, R = Math.min(width, height) / 2
        c.reset(); c.clearRect(0, 0, width, height)
        if (R < 60) return
        const r = R * 0.925, span = 0.78, N = 20
        // from/to: angle where the fill starts and ends (fill grows upward).
        function arcGauge(from, dir, value, label) {
            const known = value >= 0, f = known ? Math.max(0, Math.min(1, value / 100)) : 0
            const col = f >= 0.9 ? Theme.attention : Theme.accent
            const seg = span / N, gap = seg * 0.22
            for (let i = 0; i < N; ++i) {
                const a0 = from + dir * i * seg, a1 = from + dir * ((i + 1) * seg - gap)
                const lo = Math.min(a0, a1), hi = Math.max(a0, a1)
                const lit = known && (i + 0.5) / N <= f
                if (lit) {
                    c.strokeStyle = rgba(col, 0.20); c.lineWidth = 10
                    c.beginPath(); c.arc(cx, cy, r, lo, hi); c.stroke()
                }
                c.strokeStyle = lit ? rgba(col, 0.95) : rgba(Theme.line, 0.9); c.lineWidth = lit ? 3.5 : 2.5
                c.beginPath(); c.arc(cx, cy, r, lo, hi); c.stroke()
            }
            // End caps.
            c.strokeStyle = rgba(Theme.text, 0.6); c.lineWidth = 1
            for (const a of [from, from + dir * span]) {
                c.beginPath(); c.moveTo(cx + Math.cos(a) * (r - 9), cy + Math.sin(a) * (r - 9))
                c.lineTo(cx + Math.cos(a) * (r + 9), cy + Math.sin(a) * (r + 9)); c.stroke()
            }
        }
        // Left arc: starts lower-left, grows up. Right arc: starts lower-right, grows up.
        arcGauge(Math.PI + span / 2, -1, cpu, "CPU")
        arcGauge(span / 2, -1, memory, "MEM")

        // AI link: a short solid arc at the bottom, lit when Ask's model answers.
        const col = aiOnline ? Theme.accent : Theme.attention
        const b0 = Math.PI / 2 - 0.16, b1 = Math.PI / 2 + 0.16
        if (aiOnline) { c.strokeStyle = rgba(col, 0.2); c.lineWidth = 10; c.beginPath(); c.arc(cx, cy, r, b0, b1); c.stroke() }
        c.strokeStyle = rgba(col, aiOnline ? 0.95 : 0.6); c.lineWidth = 3.5
        c.beginPath(); c.arc(cx, cy, r, b0, b1); c.stroke()
    }

    // Readouts (crisp text on dark plates) in the band between sphere and rings.
    readonly property real ringR: Math.min(width, height) / 2
    component Readout: Rectangle {
        id: ro
        property string label: ""
        property string value: ""
        property color tone: Theme.text
        width: Math.max(labelText.implicitWidth, valueText.implicitWidth) + 14; height: col.implicitHeight + 8
        radius: 3
        color: Theme.shade(0.6)
        border.width: 1; border.color: Qt.rgba(ro.tone.r, ro.tone.g, ro.tone.b, 0.35)
        Column {
            id: col
            anchors.centerIn: parent; spacing: 0
            Text { id: labelText; anchors.horizontalCenter: parent.horizontalCenter; text: ro.label; color: Theme.muted
                   font.family: Theme.monoFont; font.pixelSize: 9; font.letterSpacing: Theme.caps ? 1.5 : 0.3 }
            Text { id: valueText; anchors.horizontalCenter: parent.horizontalCenter; text: ro.value; color: ro.tone
                   font.family: Theme.monoFont; font.pixelSize: Math.max(12, gauges.ringR * 0.04); font.bold: true }
        }
    }
    Readout {
        visible: gauges.ringR >= 60
        x: gauges.width / 2 - gauges.ringR * 0.78 - width / 2; y: gauges.height / 2 - height / 2
        label: "CPU"; value: gauges.cpu >= 0 ? Math.round(gauges.cpu) + "%" : "—"
        tone: gauges.cpu >= 90 ? Theme.attention : Theme.text
    }
    Readout {
        visible: gauges.ringR >= 60
        x: gauges.width / 2 + gauges.ringR * 0.78 - width / 2; y: gauges.height / 2 - height / 2
        label: "MEM"; value: gauges.memory >= 0 ? Math.round(gauges.memory) + "%" : "—"
        tone: gauges.memory >= 90 ? Theme.attention : Theme.text
    }
    Readout {
        visible: gauges.ringR >= 60
        x: gauges.width / 2 - width / 2; y: gauges.height / 2 + gauges.ringR * 0.78 - height / 2
        label: "AI LINK"; value: gauges.aiWord || (gauges.aiOnline ? "ONLINE" : "OFFLINE")
        tone: gauges.aiOnline ? Theme.accent : Theme.attention
    }
}
