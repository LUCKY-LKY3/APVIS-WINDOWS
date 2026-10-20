import QtQuick
import "../theme"

// HUD radar rings around the Nucleus (owner direction 2026-09-24: full HUD).
// Each layer is painted once into a texture and then only rotated, each at its
// own speed and direction, so the core feels alive at almost no per-frame cost.
// Decorative only; real state stays on NucleusFrame's nodes.
Item {
    id: rings
    property real time: 0
    property bool reducedMotion: false
    readonly property real t: reducedMotion ? 0 : time

    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }

    // A cached ring layer: `draw(ctx, cx, cy, r)` paints once; `speed` is deg/s.
    component Layer: Canvas {
        id: layer
        property real speed: 0
        property var draw: null
        anchors.fill: parent
        antialiasing: true
        renderTarget: Canvas.FramebufferObject
        rotation: (rings.t * speed) % 360
        transformOrigin: Item.Center
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()
        onPaint: {
            const c = getContext("2d"); c.reset(); c.clearRect(0, 0, width, height)
            if (draw && width > 40) draw(c, width / 2, height / 2, Math.min(width, height) / 2)
        }
    }

    // Energy streaks: glowing filaments sweeping around the core.
    Layer {
        speed: -3.2
        draw: function(c, cx, cy, R) {
            c.globalCompositeOperation = "lighter"
            // Short glowing arcs orbiting in a tight band just outside the sphere,
            // tapering at both ends like light trails.
            for (let i = 0; i < 6; ++i) {
                const a0 = i * 1.05 + (i % 2) * 0.35, sweep = 0.55 + (i % 3) * 0.25
                const r = R * (0.835 + (i % 3) * 0.018)
                const colour = i === 4 ? Theme.warm : i % 3 === 0 ? Theme.text : Theme.accent
                const segs = 28
                for (let s = 0; s < segs; ++s) {
                    const f = s / segs, taper = Math.sin(f * Math.PI)
                    const a = a0 + f * sweep, b = a0 + (f + 1 / segs) * sweep
                    for (let pass = 0; pass < 2; ++pass) {
                        c.lineWidth = pass ? 1.2 * taper + 0.3 : 5 * taper
                        c.strokeStyle = rings.rgba(colour, pass ? 0.85 * taper : 0.10 * taper)
                        c.beginPath(); c.arc(cx, cy, r, a, b); c.stroke()
                    }
                }
            }
        }
    }
    // Degree scale with numbered major ticks.
    Layer {
        speed: 1.4
        draw: function(c, cx, cy, R) {
            const r = R * 0.965
            for (let d = 0; d < 360; d += 2) {
                const a = d * Math.PI / 180, major = d % 30 === 0, mid = d % 10 === 0
                const len = major ? R * 0.035 : mid ? R * 0.02 : R * 0.01
                c.strokeStyle = rings.rgba(major ? Theme.text : Theme.accent, major ? 0.7 : mid ? 0.45 : 0.25)
                c.lineWidth = major ? 1.2 : 0.7
                c.beginPath(); c.moveTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r)
                c.lineTo(cx + Math.cos(a) * (r - len), cy + Math.sin(a) * (r - len)); c.stroke()
                if (major) {
                    c.save(); c.translate(cx + Math.cos(a) * (r - R * 0.07), cy + Math.sin(a) * (r - R * 0.07)); c.rotate(a + Math.PI / 2)
                    c.fillStyle = rings.rgba(Theme.text, 0.75); c.font = Math.max(9, R * 0.03) + "px monospace"; c.textAlign = "center"
                    c.fillText(("00" + d).slice(-3), 0, 0); c.restore()
                }
            }
        }
    }
    // Bracketed segment ring (counter-rotating).
    Layer {
        speed: -5.5
        draw: function(c, cx, cy, R) {
            const r = R * 0.885
            c.lineWidth = 2.2
            for (let k = 0; k < 6; ++k) {
                const a = k * Math.PI / 3
                c.strokeStyle = rings.rgba(k === 1 ? Theme.warm : Theme.accent, 0.65)
                c.beginPath(); c.arc(cx, cy, r, a, a + 0.42); c.stroke()
                c.lineWidth = 1
                c.beginPath(); c.moveTo(cx + Math.cos(a) * (r - 6), cy + Math.sin(a) * (r - 6)); c.lineTo(cx + Math.cos(a) * (r + 6), cy + Math.sin(a) * (r + 6)); c.stroke()
                c.lineWidth = 2.2
            }
            c.strokeStyle = rings.rgba(Theme.accent, 0.18); c.lineWidth = 0.8
            c.beginPath(); c.arc(cx, cy, r, 0, Math.PI * 2); c.stroke()
        }
    }
    // Fine dashed inner ring, faster.
    Layer {
        speed: 9
        draw: function(c, cx, cy, R) {
            const r = R * 0.80
            c.strokeStyle = rings.rgba(Theme.accent, 0.45); c.lineWidth = 1
            for (let d = 0; d < 360; d += 4) {
                if (d % 40 < 8) continue
                const a = d * Math.PI / 180
                c.beginPath(); c.arc(cx, cy, r, a, a + 0.035); c.stroke()
            }
            for (let k = 0; k < 3; ++k) {
                const a = k * 2 * Math.PI / 3
                c.fillStyle = rings.rgba(Theme.text, 0.9)
                c.beginPath(); c.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r, 2.2, 0, Math.PI * 2); c.fill()
            }
        }
    }
    // Radar sweep.
    Layer {
        speed: 24
        opacity: 0.8
        draw: function(c, cx, cy, R) {
            const r = R * 0.79, steps = 40
            for (let s = 0; s < steps; ++s) {
                const a0 = -s * 0.018, a1 = a0 - 0.02
                c.fillStyle = rings.rgba(Theme.accent, 0.10 * (1 - s / steps))
                c.beginPath(); c.moveTo(cx, cy); c.arc(cx, cy, r, a1, a0); c.closePath(); c.fill()
            }
            c.strokeStyle = rings.rgba(Theme.accent, 0.55); c.lineWidth = 1
            c.beginPath(); c.moveTo(cx, cy); c.lineTo(cx + r, cy); c.stroke()
        }
    }
}
