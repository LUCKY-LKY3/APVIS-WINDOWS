import QtQuick
import "../theme"

// Emerald smoke and faint dust behind Home. Painted once (cheap on the OptiPlex)
// and only drifted/scaled afterwards, the technique APVIS 7.0.1 used for its haze.
Item {
    id: atmosphere
    property real phase: 0            // seconds; drives a very slow drift
    property real focusX: 0.5         // where the smoke gathers (the Nucleus)
    property real focusY: 0.45
    property bool reducedMotion: false
    readonly property real t: reducedMotion ? 0 : phase * 0.05

    Canvas {
        id: smoke
        x: -40 + Math.sin(atmosphere.t) * 18
        y: -30 + Math.cos(atmosphere.t * .77) * 12
        width: (atmosphere.width + 80) / 2
        height: (atmosphere.height + 60) / 2
        scale: 2.0 + Math.sin(atmosphere.t * .63) * .025
        transformOrigin: Item.TopLeft
        opacity: .92 + Math.sin(atmosphere.t * 1.3) * .05
        renderTarget: Canvas.FramebufferObject
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()
        function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
        onPaint: {
            const ctx = getContext("2d"), w = width, h = height
            ctx.clearRect(0, 0, w, h)
            const fx = w * atmosphere.focusX, fy = h * atmosphere.focusY
            // A deep glow where the Nucleus sits.
            const core = ctx.createRadialGradient(fx, fy, 10, fx, fy, w * .42)
            core.addColorStop(0, rgba(Theme.glow, .34))
            core.addColorStop(.5, rgba(Theme.glow, .10))
            core.addColorStop(1, Theme.css(Theme.shadeBase, 0))
            ctx.fillStyle = core; ctx.fillRect(0, 0, w, h)
            // Wisps: overlapping soft clouds, denser near the core, a few cool-grey.
            for (let i = 0; i < 26; ++i) {
                const a = i * 2.39996, d = 0.10 + ((i * 0.137) % 0.55)
                const x = fx + Math.cos(a) * w * d * 0.9, y = fy + Math.sin(a) * h * d * 0.8
                const r = w * (0.05 + ((i * 0.071) % 0.09))
                const g = ctx.createRadialGradient(x, y, 2, x, y, r)
                const alpha = (0.16 - d * 0.14) * (i % 5 === 0 ? 0.8 : 1)
                g.addColorStop(0, i % 5 === 0 ? rgba(Theme.muted, alpha * 0.7) : rgba(Theme.accentSoft, alpha))
                g.addColorStop(.5, rgba(Theme.glow, alpha * .45))
                g.addColorStop(1, Theme.css(Theme.shadeBase, 0))
                ctx.fillStyle = g; ctx.fillRect(0, 0, w, h)
            }
            // Faint dust.
            for (let i = 0; i < 110; ++i) {
                const x = (i * 151.7) % w, y = (i * 79.3) % h
                ctx.fillStyle = i % 19 ? rgba(Theme.accentSoft, .16) : rgba(Theme.accent, .34)
                ctx.beginPath(); ctx.arc(x, y, i % 19 ? .45 : 1.0, 0, Math.PI * 2); ctx.fill()
            }
        }
    }
}
