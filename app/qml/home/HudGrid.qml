import QtQuick
import "../theme"

// Blueprint grid, vignette and screen-corner brackets behind Home. Static:
// painted once per size change, never per frame.
Canvas {
    id: grid
    renderTarget: Canvas.FramebufferObject
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    Component.onCompleted: requestPaint()
    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
    onPaint: {
        const c = getContext("2d"), w = width, h = height
        c.reset(); c.clearRect(0, 0, w, h)
        // Minor and major grid lines.
        for (let x = 0; x <= w; x += 32) {
            c.strokeStyle = rgba(Theme.accent, x % 160 === 0 ? 0.09 : 0.04); c.lineWidth = 1
            c.beginPath(); c.moveTo(x + .5, 0); c.lineTo(x + .5, h); c.stroke()
        }
        for (let y = 0; y <= h; y += 32) {
            c.strokeStyle = rgba(Theme.accent, y % 160 === 0 ? 0.09 : 0.04)
            c.beginPath(); c.moveTo(0, y + .5); c.lineTo(w, y + .5); c.stroke()
        }
        // Small crosses where major lines meet.
        c.strokeStyle = rgba(Theme.accent, 0.16)
        for (let x = 160; x < w; x += 160) for (let y = 160; y < h; y += 160) {
            c.beginPath(); c.moveTo(x - 4, y + .5); c.lineTo(x + 5, y + .5); c.moveTo(x + .5, y - 4); c.lineTo(x + .5, y + 5); c.stroke()
        }
        // Vignette so the grid fades toward the edges.
        const v = c.createRadialGradient(w / 2, h * 0.46, Math.min(w, h) * 0.2, w / 2, h * 0.46, Math.max(w, h) * 0.75)
        v.addColorStop(0, Theme.css(Theme.shadeBase, 0)); v.addColorStop(1, Theme.css(Theme.shadeBase, 0.55))
        c.fillStyle = v; c.fillRect(0, 0, w, h)
        // Screen-corner brackets.
        c.strokeStyle = rgba(Theme.accent, 0.55); c.lineWidth = 1.5
        const L = 26, m = 8
        const corners = [[m, m, 1, 1], [w - m, m, -1, 1], [m, h - m, 1, -1], [w - m, h - m, -1, -1]]
        for (const k of corners) {
            c.beginPath(); c.moveTo(k[0], k[1] + k[3] * L); c.lineTo(k[0], k[1]); c.lineTo(k[0] + k[2] * L, k[1]); c.stroke()
        }
    }
}
