import QtQuick
import "../theme"

// Light around the core: a soft bloom that breathes with the Nucleus, a slow
// corona of rays, and a rim light that travels round the outer ring. Each layer
// is painted once; per frame only opacity and rotation change (cheap on the
// OptiPlex GPU). Decorative only.
Item {
    id: g
    property real time: 0
    property real energy: 1
    property bool reducedMotion: false
    readonly property real t: reducedMotion ? 0 : time
    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }

    component Layer: Canvas {
        id: layer
        property var draw: null
        anchors.fill: parent
        antialiasing: true
        renderTarget: Canvas.FramebufferObject
        transformOrigin: Item.Center
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()
        Connections { target: Theme; function onAccentNameChanged() { layer.requestPaint() } }
        onPaint: {
            const c = getContext("2d"); c.reset(); c.clearRect(0, 0, width, height)
            if (draw && width > 40) draw(c, width / 2, height / 2, Math.min(width, height) / 2)
        }
    }

    // Bloom: light pooling around the sphere and spilling past the rings.
    Layer {
        opacity: (0.78 + 0.22 * Math.sin(g.t * 0.7)) * Math.min(1.15, 0.6 + g.energy * 0.45)
        draw: function(c, cx, cy, R) {
            const b = c.createRadialGradient(cx, cy, R * 0.05, cx, cy, R)
            b.addColorStop(0, g.rgba(Theme.glow, 0.30))
            b.addColorStop(0.5, g.rgba(Theme.glow, 0.20))
            b.addColorStop(0.72, g.rgba(Theme.accent, 0.12))
            b.addColorStop(0.86, g.rgba(Theme.accent, 0.05))
            b.addColorStop(1, g.rgba(Theme.accent, 0))
            c.fillStyle = b; c.fillRect(0, 0, 2 * cx, 2 * cy)
        }
    }
    // Corona: faint rays between the sphere and the rings (turns slowly).
    Layer {
        rotation: (g.t * 1.6) % 360
        opacity: 0.9
        draw: function(c, cx, cy, R) {
            c.globalCompositeOperation = "lighter"
            for (let i = 0; i < 64; ++i) {
                const a = i / 64 * Math.PI * 2 + Math.sin(i * 12.9898) * 0.03
                const len = 0.16 + 0.12 * Math.abs(Math.sin(i * 78.233)), w = 0.006 + 0.012 * Math.abs(Math.sin(i * 3.7))
                const r0 = R * 0.72, r1 = R * (0.72 + len)
                const gr = c.createLinearGradient(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0, cx + Math.cos(a) * r1, cy + Math.sin(a) * r1)
                gr.addColorStop(0, g.rgba(i % 9 === 0 ? Theme.text : Theme.accent, 0.10))
                gr.addColorStop(1, g.rgba(Theme.accent, 0))
                c.fillStyle = gr
                c.beginPath(); c.moveTo(cx + Math.cos(a - w) * r0, cy + Math.sin(a - w) * r0)
                c.lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1)
                c.lineTo(cx + Math.cos(a + w) * r0, cy + Math.sin(a + w) * r0); c.closePath(); c.fill()
            }
        }
    }
    // Rim light: two comets of light running round the outer edge.
    Layer {
        rotation: (-g.t * 10) % 360
        draw: function(c, cx, cy, R) {
            c.globalCompositeOperation = "lighter"
            const r = R * 0.985
            for (const base of [0, Math.PI]) {
                const n = 50
                for (let s = 0; s < n; ++s) {
                    const f = s / n, a = base - f * 1.3, fade = Math.pow(1 - f, 1.8)
                    c.strokeStyle = g.rgba(Theme.accent, 0.10 * fade); c.lineWidth = 8
                    c.beginPath(); c.arc(cx, cy, r, a - 1.3 / n, a); c.stroke()
                    c.strokeStyle = g.rgba(s < 3 ? Theme.text : Theme.accent, 0.85 * fade); c.lineWidth = 1.6
                    c.beginPath(); c.arc(cx, cy, r, a - 1.3 / n, a); c.stroke()
                }
                const hx = cx + Math.cos(base) * r, hy = cy + Math.sin(base) * r
                const head = c.createRadialGradient(hx, hy, 0, hx, hy, 12)
                head.addColorStop(0, g.rgba(Theme.text, 0.9)); head.addColorStop(0.4, g.rgba(Theme.accent, 0.35)); head.addColorStop(1, g.rgba(Theme.accent, 0))
                c.fillStyle = head; c.fillRect(hx - 12, hy - 12, 24, 24)
            }
        }
    }
}
