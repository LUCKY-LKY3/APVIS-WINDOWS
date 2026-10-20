import QtQuick
import "../theme"

// The room behind Home: a holographic floor grid receding to a glowing horizon,
// soft light beams from above and three depths of drifting dust (parallax).
// Static layers are painted once; dust layers are cached tiles only translated.
Item {
    id: backdrop
    property real phase: 0
    property bool reducedMotion: false
    property real horizon: 0.64          // fraction of height where the floor meets the dark
    readonly property real t: reducedMotion ? 0 : phase
    clip: true

    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }

    // Beams, horizon glow and the perspective floor grid.
    Canvas {
        id: room
        anchors.fill: parent
        renderTarget: Canvas.FramebufferObject
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()
        onPaint: {
            const c = getContext("2d"), w = width, h = height, hy = h * backdrop.horizon, vx = w * 0.5
            c.reset(); c.clearRect(0, 0, w, h)
            c.globalCompositeOperation = "lighter"
            // Light beams falling from the ceiling.
            for (let b = 0; b < 5; ++b) {
                const x = w * (0.16 + b * 0.17), spread = w * (0.05 + (b % 2) * 0.03)
                const g = c.createLinearGradient(0, 0, 0, hy)
                g.addColorStop(0, backdrop.rgba(Theme.accent, 0.050)); g.addColorStop(1, backdrop.rgba(Theme.accent, 0))
                c.fillStyle = g
                c.beginPath(); c.moveTo(x - 10, 0); c.lineTo(x + 10, 0); c.lineTo(x + spread, hy); c.lineTo(x - spread, hy); c.closePath(); c.fill()
            }
            // Horizon band.
            const hg = c.createLinearGradient(0, hy - h * 0.12, 0, hy + h * 0.06)
            hg.addColorStop(0, Theme.css(Theme.shadeBase, 0)); hg.addColorStop(0.7, backdrop.rgba(Theme.glow, 0.28))
            hg.addColorStop(0.86, backdrop.rgba(Theme.accent, 0.20)); hg.addColorStop(1, Theme.css(Theme.shadeBase, 0))
            c.fillStyle = hg; c.fillRect(0, hy - h * 0.12, w, h * 0.18)
            const hl = c.createLinearGradient(0, 0, w, 0)
            hl.addColorStop(0, Theme.css(Theme.shadeBase, 0)); hl.addColorStop(0.5, backdrop.rgba(Theme.accent, 0.22)); hl.addColorStop(1, Theme.css(Theme.shadeBase, 0))
            c.strokeStyle = hl; c.lineWidth = 1
            c.beginPath(); c.moveTo(0, hy + .5); c.lineTo(w, hy + .5); c.stroke()
            // Floor grid: lines to the vanishing point, and rows closing up toward the horizon.
            for (let i = -18; i <= 18; ++i) {
                const xb = vx + i * w * 0.09
                const g = c.createLinearGradient(0, hy, 0, h)
                g.addColorStop(0, backdrop.rgba(Theme.accent, 0.02)); g.addColorStop(1, backdrop.rgba(Theme.accent, 0.20))
                c.strokeStyle = g; c.lineWidth = 1
                c.beginPath(); c.moveTo(vx + (xb - vx) * 0.02, hy); c.lineTo(xb, h); c.stroke()
            }
            for (let r = 1; r <= 14; ++r) {
                const f = Math.pow(r / 14, 2.2), y = hy + (h - hy) * f
                c.strokeStyle = backdrop.rgba(Theme.accent, 0.03 + 0.17 * f); c.lineWidth = 1
                c.beginPath(); c.moveTo(0, y + .5); c.lineTo(w, y + .5); c.stroke()
            }
            // Pool of light on the floor under the Nucleus.
            const pool = c.createRadialGradient(vx, hy + (h - hy) * 0.25, 5, vx, hy + (h - hy) * 0.25, w * 0.32)
            pool.addColorStop(0, backdrop.rgba(Theme.accent, 0.14)); pool.addColorStop(1, Theme.css(Theme.shadeBase, 0))
            c.save(); c.translate(0, 0); c.scale(1, 0.35); c.fillStyle = pool
            c.fillRect(0, (hy - h * 0.05) / 0.35, w, (h - hy + h * 0.1) / 0.35); c.restore()
        }
    }

    // Three depths of dust: far = small/slow/dim, near = larger/faster/brighter.
    component Dust: Item {
        id: dust
        property int count: 60
        property real size: 1
        property real speed: 4        // px per second, to the left
        property real alpha: 0.3
        property int seed: 1
        anchors.fill: parent
        readonly property real offset: (backdrop.t * speed) % Math.max(1, width)
        Repeater {
            model: 2
            Canvas {
                required property int index
                width: dust.width; height: dust.height
                x: index * dust.width - dust.offset
                y: Math.sin(backdrop.t * 0.05 + dust.seed) * 6
                renderTarget: Canvas.FramebufferObject
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
                Component.onCompleted: requestPaint()
                onPaint: {
                    const c = getContext("2d"), w = width, h = height
                    c.reset(); c.clearRect(0, 0, w, h)
                    for (let i = 0; i < dust.count; ++i) {
                        const hx = Math.abs(Math.sin(i * 12.9898 + dust.seed * 78.233) * 43758.5453) % 1
                        const hy = Math.abs(Math.sin(i * 39.3468 + dust.seed * 11.135) * 24634.6345) % 1
                        const x = hx * w, y = hy * h, r = dust.size * (0.6 + (i % 5) * 0.2)
                        const g = c.createRadialGradient(x, y, 0, x, y, r * 3)
                        g.addColorStop(0, backdrop.rgba(i % 11 === 0 ? Theme.text : Theme.accent, dust.alpha))
                        g.addColorStop(1, Theme.css(Theme.shadeBase, 0))
                        c.fillStyle = g; c.beginPath(); c.arc(x, y, r * 3, 0, Math.PI * 2); c.fill()
                    }
                }
            }
        }
    }
    Dust { count: 90; size: 0.6; speed: 2.2; alpha: 0.35; seed: 3 }
    Dust { count: 40; size: 1.1; speed: 5.5; alpha: 0.45; seed: 7 }
    Dust { count: 14; size: 2.0; speed: 11; alpha: 0.30; seed: 13 }
}
