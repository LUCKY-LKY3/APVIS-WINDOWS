import QtQuick
import "../theme"

// Engineered "neural fabric" around the particle sphere, after APVIS 7.0.1:
// neural links, sweeping particle ribbons, latitude bands, partial orbit rails
// with end nodes, segmented outer instrumentation and physical light/shade.
// It is painted once into a texture and only rotated, so it adds richness
// without adding per-frame work on the OptiPlex. Decorative only: it never
// shows state (state lives in NucleusFrame's real nodes).
Item {
    id: fabric
    property real time: 0
    property real spin: 0.012         // radians per second of the cached layer
    property bool reducedMotion: false

    Canvas {
        id: cache
        anchors.fill: parent
        antialiasing: true
        renderTarget: Canvas.FramebufferObject
        rotation: fabric.reducedMotion ? 0 : (fabric.time * fabric.spin * 180 / Math.PI) % 360
        transformOrigin: Item.Center
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()

        function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
        function fract(v) { return v - Math.floor(v) }
        function hash(i, s) { return fract(Math.sin(i * 91.713 + s * 17.17) * 43758.5453) }
        function point(i, n, span, cx, cy) {
            const golden = 2.399963229728653, z = 1 - 2 * (i + .5) / n
            const radial = Math.sqrt(Math.max(0, 1 - z * z)), a = i * golden
            const depth = radial * Math.sin(a), s = .78 + .22 * (depth + 1) * .5
            return { x: cx + radial * Math.cos(a) * span * s, y: cy + z * span * .96, depth: depth }
        }

        onPaint: {
            if (width < 40 || height < 40) return
            const c = getContext("2d"), cx = width / 2, cy = height / 2, span = Math.min(width, height) * .36
            const A = Theme.accent, S = Theme.text, W = Theme.warm, G = Theme.glow
            c.clearRect(0, 0, width, height)
            c.save(); c.globalCompositeOperation = "lighter"

            // Neural links between near-side points of the shell.
            const n = 1800
            c.lineWidth = .5
            for (let i = 0; i < n; i += 11) {
                const a = point(i, n, span, cx, cy), b = point((i * 7 + 113) % n, n, span, cx, cy)
                if (a.depth > -.2 && b.depth > -.2) {
                    c.strokeStyle = rgba(A, .10 + .10 * (a.depth + 1) * .5)
                    c.beginPath(); c.moveTo(a.x, a.y); c.lineTo(b.x, b.y); c.stroke()
                }
            }
            // Sweeping particle ribbons across the shell.
            for (let r = 0; r < 6; ++r) {
                const rot = -1.0 + r * .34, cr = Math.cos(rot), sr = Math.sin(rot)
                const rx = span * (.80 + r * .03), ry = span * (.40 + (r % 3) * .11)
                for (let s = 0; s < 190; ++s) {
                    const t = s * Math.PI * 2 / 190 + r * .47
                    const warp = 1 + Math.sin(t * 3 + r * 1.7) * .05
                    const px = Math.cos(t) * rx * warp, py = Math.sin(t) * ry
                    const x = cx + px * cr - py * sr, y = cy + px * sr + py * cr
                    const front = .45 + .55 * Math.max(0, Math.sin(t + r * .63))
                    c.fillStyle = s % 67 === 0 ? rgba(W, .8) : rgba(A, .10 + front * .34)
                    c.beginPath(); c.arc(x, y, .5 + front * .7, 0, Math.PI * 2); c.fill()
                }
            }
            // Latitude bands.
            for (let band = -4; band <= 4; ++band) {
                const y = cy + band * span * .19, f = band / 5.2
                const rx = span * Math.sqrt(Math.max(.08, 1 - f * f)), ry = span * (.09 + Math.abs(band) * .01)
                c.strokeStyle = band === 0 ? rgba(A, .34) : rgba(A, .13); c.lineWidth = band === 0 ? 1 : .6
                c.beginPath()
                for (let s = 0; s <= 72; ++s) { const a = s * Math.PI * 2 / 72, x = cx + Math.cos(a) * rx, yy = y + Math.sin(a) * ry; s ? c.lineTo(x, yy) : c.moveTo(x, yy) }
                c.stroke()
            }
            c.restore()

            // Light and shade: a forward-left highlight, the far rim falling off.
            c.save()
            const shade = c.createRadialGradient(cx - span * .2, cy - span * .2, span * .2, cx, cy, span * 1.08)
            shade.addColorStop(0, Theme.css(Theme.shadeBase, 0)); shade.addColorStop(.65, Theme.css(Theme.shadeBase, .02)); shade.addColorStop(1, Theme.css(Theme.shadeBase, .42))
            c.fillStyle = shade; c.beginPath(); c.arc(cx, cy, span * 1.04, 0, Math.PI * 2); c.fill()
            c.globalCompositeOperation = "lighter"
            const light = c.createRadialGradient(cx - span * .32, cy - span * .34, 0, cx - span * .32, cy - span * .34, span * .56)
            light.addColorStop(0, rgba(S, .07)); light.addColorStop(.45, rgba(A, .03)); light.addColorStop(1, Theme.css(Theme.shadeBase, 0))
            c.fillStyle = light; c.beginPath(); c.arc(cx - span * .32, cy - span * .34, span * .56, 0, Math.PI * 2); c.fill()

            // Partial orbit rails with glowing end nodes.
            for (let o = 0; o < 4; ++o) {
                const radius = span * (1.08 + o * .05), start = .55 + o * 1.21, end = start + 1.1
                c.strokeStyle = o === 2 ? rgba(W, .38) : rgba(A, .26); c.lineWidth = o === 2 ? .9 : .6
                c.beginPath(); c.arc(cx, cy, radius, start, end); c.stroke()
                const nx = cx + Math.cos(end) * radius, ny = cy + Math.sin(end) * radius
                const g = c.createRadialGradient(nx, ny, 0, nx, ny, 7)
                g.addColorStop(0, o === 2 ? rgba(W, .9) : rgba(S, .9)); g.addColorStop(.3, rgba(A, .45)); g.addColorStop(1, Theme.css(Theme.shadeBase, 0))
                c.fillStyle = g; c.beginPath(); c.arc(nx, ny, 7, 0, Math.PI * 2); c.fill()
            }
            // Segmented outer instrumentation.
            for (let rail = 0; rail < 6; ++rail) {
                const radius = span * (1.30 + rail * .028)
                c.strokeStyle = rail === 2 ? rgba(S, .34) : rgba(A, .10 + rail * .02)
                c.lineWidth = rail === 2 ? .9 : .55
                for (let seg = 0; seg < 36; ++seg) {
                    if ((seg + rail * 3) % 7 === 0 || (seg * 5 + rail) % 11 === 0) continue
                    const a = seg * Math.PI * 2 / 36 + rail * .07
                    c.beginPath(); c.arc(cx, cy, radius, a, a + .09 + (rail % 3) * .018); c.stroke()
                }
            }
            // Keep the centre clear for the wordmark and answers.
            c.globalCompositeOperation = "destination-out"
            const hole = c.createRadialGradient(cx, cy, 0, cx, cy, span * .42)
            hole.addColorStop(0, Theme.css(Theme.shadeBase, 1)); hole.addColorStop(.62, Theme.css(Theme.shadeBase, .85)); hole.addColorStop(1, Theme.css(Theme.shadeBase, 0))
            c.fillStyle = hole; c.beginPath(); c.arc(cx, cy, span * .42, 0, Math.PI * 2); c.fill()
            c.restore()
        }
    }
}
