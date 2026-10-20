import QtQuick

// The APVIS mark (V3, owner 2026-10-09): a miniature of the core, so the logo is the thing people see on
// Home. An outer ring broken by four gaps, a segmented reactor ring, an inner ring and a bright centre
// point, in the accent colour with a soft glow. (The earlier faceted "A" looked too much like Arch Linux.)
// Painted once per size or colour change.
Item {
    id: mark
    property color tint: Theme.accent
    property real glow: 0.6            // 0 = no glow
    implicitWidth: 64
    implicitHeight: 64

    function rgba(c, a, k) {
        k = k === undefined ? 1 : k
        return "rgba(" + Math.round(Math.min(255, c.r * 255 * k)) + "," + Math.round(Math.min(255, c.g * 255 * k)) + "," +
               Math.round(Math.min(255, c.b * 255 * k)) + "," + a + ")"
    }
    onTintChanged: art.requestPaint()
    onGlowChanged: art.requestPaint()

    Canvas {
        id: art
        anchors.fill: parent
        // Whole-pixel margins: a fractional offset made the texture sample between pixels (blurry logo).
        anchors.margins: -Math.round(Math.max(mark.width, mark.height) * 0.25)
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()
        onPaint: {
            const c = getContext("2d")
            c.reset(); c.clearRect(0, 0, width, height)
            const T = mark.tint
            const R = Math.min(mark.width, mark.height) / 2          // the mark's own radius
            // Small sizes (top bar, tabs): centre on a pixel, whole-pixel strokes, full-strength lines and
            // almost no halo, so the mark reads sharp instead of a soft smudge (3.0.7).
            const small = R < 24
            const cx = small ? Math.floor(width / 2) + 0.5 : width / 2, cy = small ? Math.floor(height / 2) + 0.5 : height / 2
            const glow = small ? mark.glow * 0.35 : mark.glow
            if (glow > 0) {
                const g = c.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.45)
                g.addColorStop(0, mark.rgba(T, 0.18 * glow)); g.addColorStop(0.55, mark.rgba(T, 0.05 * glow))
                g.addColorStop(1, mark.rgba(T, 0))
                c.fillStyle = g; c.fillRect(0, 0, width, height)
            }
            // A fine outer ring broken at the four diagonals.
            c.strokeStyle = mark.rgba(T, small ? 1 : 0.95, 1.15); c.lineWidth = small ? (R < 14 ? 1 : 1.5) : Math.max(1, R * 0.06)
            c.lineCap = small ? "butt" : "round"
            for (let i = 0; i < 4; i++) {
                const mid = i * Math.PI / 2
                c.beginPath(); c.arc(cx, cy, small ? Math.round(R * 0.92) - 0.5 : R * 0.92, mid - 0.55, mid + 0.55); c.stroke()
            }
            // Six short segments of light closer in.
            c.strokeStyle = mark.rgba(T, small ? 0.95 : 0.8); c.lineWidth = small ? (R < 14 ? 1.5 : 2) : Math.max(1, R * 0.08)
            for (let i = 0; i < 6; i++) {
                const mid = i * Math.PI / 3 + Math.PI / 6
                c.beginPath(); c.arc(cx, cy, small ? Math.round(R * 0.62) : R * 0.62, mid - 0.32, mid + 0.32); c.stroke()
            }
            // The bright core of light.
            const p = c.createRadialGradient(cx, cy, 0, cx, cy, R * 0.34)
            p.addColorStop(0, mark.rgba(Theme.markGlint, 1)); p.addColorStop(0.35, mark.rgba(T, 1, 1.2))
            p.addColorStop(0.7, mark.rgba(T, 0.35)); p.addColorStop(1, mark.rgba(T, 0))
            c.fillStyle = p; c.beginPath(); c.arc(cx, cy, R * 0.34, 0, Math.PI * 2); c.fill()
        }
    }
    Accessible.role: Accessible.Graphic
    Accessible.name: "APVIS"
}
