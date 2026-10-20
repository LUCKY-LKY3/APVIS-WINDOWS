import QtQuick
import "../theme"

// Engineered HUD frame around the particle sphere: soft core glow behind,
// precise rings/ticks around, and real state nodes. Repaints only on change.
Canvas {
    id: frame
    property bool hasFocus: false
    property int approvals: 0
    property int running: 0
    property int attention: 0      // interrupted + unreadable records
    property real apertureAmount: 0
    renderStrategy: Canvas.Cooperative

    onHasFocusChanged: requestPaint()
    onApprovalsChanged: requestPaint()
    onRunningChanged: requestPaint()
    onAttentionChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    Connections { target: Theme; function onAccentNameChanged() { frame.requestPaint() } }

    onPaint: {
        const c = getContext("2d")
        c.reset()
        const cx = width / 2, cy = height / 2
        const s = Math.min(width, height)
        const twoPi = Math.PI * 2
        const core = s * 0.36

        const glow = c.createRadialGradient(cx, cy, 2, cx, cy, core * 1.25)
        glow.addColorStop(0, Qt.rgba(Theme.glow.r, Theme.glow.g, Theme.glow.b, 0.55))
        glow.addColorStop(0.55, Qt.rgba(Theme.glow.r, Theme.glow.g, Theme.glow.b, 0.18))
        glow.addColorStop(1, Qt.rgba(Theme.glow.r, Theme.glow.g, Theme.glow.b, 0))
        c.fillStyle = glow
        c.beginPath(); c.arc(cx, cy, core * 1.25, 0, twoPi); c.fill()

        const outer = s * 0.455, tick = s * 0.425, arc = s * 0.405
        c.lineWidth = 0.8
        c.strokeStyle = Theme.line
        c.beginPath(); c.arc(cx, cy, outer, 0, twoPi); c.stroke()
        c.lineWidth = 1.6
        c.strokeStyle = Theme.accentSoft
        c.beginPath(); c.arc(cx, cy, arc, -Math.PI * 0.86, -Math.PI * 0.14); c.stroke()
        c.beginPath(); c.arc(cx, cy, arc, Math.PI * 0.14, Math.PI * 0.86); c.stroke()
        for (let i = 0; i < 72; ++i) {
            const a = i * twoPi / 72 - Math.PI / 2
            const major = i % 9 === 0
            const r0 = tick - (major ? 7 : 3), r1 = tick + (major ? 7 : 3)
            c.lineWidth = major ? 1.4 : 0.7
            c.strokeStyle = major ? Theme.accentSoft : Theme.line
            c.beginPath()
            c.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0)
            c.lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1)
            c.stroke()
        }

        // Real state only: Focus (accent) and attention records (amber).
        const nodes = []
        if (hasFocus) nodes.push({ angle: -2.45, color: Theme.accent })
        if (approvals > 0) nodes.push({ angle: -0.42, color: Theme.attention })
        if (running > 0) nodes.push({ angle: 0.72, color: Theme.attention })
        if (attention > 0) nodes.push({ angle: 2.15, color: Theme.attention })
        for (let i = 0; i < nodes.length; ++i) {
            const n = nodes[i]
            const x0 = cx + Math.cos(n.angle) * arc, y0 = cy + Math.sin(n.angle) * arc
            const x1 = cx + Math.cos(n.angle) * outer, y1 = cy + Math.sin(n.angle) * outer
            c.lineWidth = 1
            c.strokeStyle = n.color
            c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke()
            c.fillStyle = n.color
            c.beginPath(); c.arc(x1, y1, 5, 0, twoPi); c.fill()
        }
    }
}
