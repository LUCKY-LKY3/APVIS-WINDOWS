import QtQuick

// A HUD-style box: two cut corners, optional accent brackets. Used as the
// background of buttons, dock tiles, panels and the Ask bar. Paints once per
// size or colour change, so it costs nothing while the screen is still.
Canvas {
    id: box
    property color fill: Theme.raised
    property real fillOpacity: 0.8
    // Optional vertical gradient: fill at the top to fill2 at the bottom.
    property color fill2: fill
    property real fill2Opacity: -1
    property color stroke: Theme.line
    property real strokeWidth: 1
    property real cut: 8
    property bool brackets: false
    property color bracketColour: Theme.accent
    // A lit top edge (bright in the middle, fading to the corners).
    property bool edgeGlow: false
    property color glowColour: Theme.accent
    // Painting is the expensive part (CPU raster + texture upload), so it is lazy (3.0.7, V4 step 1):
    // hidden layers (hover/focus rings at opacity 0) wait until they show, sub-pixel size jitter is
    // ignored, and a size that keeps changing (opening/rise-in animations, live lists) repaints at most
    // every 90 ms and once more when it settles.
    property bool dirtyArt: true
    property int paintedW: -1
    property int paintedH: -1
    readonly property bool shownNow: visible && opacity > 0.001 && width >= 1 && height >= 1
    function schedule() { dirtyArt = true; if (shownNow) requestPaint() }
    function sizeChanged() {
        const w = Math.round(width), h = Math.round(height)
        if (w === paintedW && h === paintedH) return
        if (paintedW < 0 || !shownNow) { schedule(); return }
        if (!settle.running) settle.start()
    }
    Timer { id: settle; interval: 90; onTriggered: box.schedule() }
    onShownNowChanged: if (shownNow && (dirtyArt || Math.round(width) !== paintedW || Math.round(height) !== paintedH)) requestPaint()
    onFillChanged: schedule()
    onFill2Changed: schedule()
    onFillOpacityChanged: schedule()
    onStrokeChanged: schedule()
    onStrokeWidthChanged: schedule()
    onBracketsChanged: schedule()
    onBracketColourChanged: schedule()
    onEdgeGlowChanged: schedule()
    onGlowColourChanged: schedule()
    Connections { target: Theme; function onStyleChanged() { box.schedule() } function onAccentNameChanged() { box.schedule() } }
    onWidthChanged: sizeChanged()
    onHeightChanged: sizeChanged()
    Component.onCompleted: schedule()
    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
    // V3 holographic (JARVIS): two cut corners, a translucent dark fill, a gold hairline with a soft glow,
    // bright corner brackets on the other two corners, and a lit inlay along the top when live.
    function paintHolo(c, w, h) {
        const o = strokeWidth / 2, k = Math.min(cut * 0.9, w / 4, h / 4)
        function outline() {
            c.beginPath()
            c.moveTo(o, o); c.lineTo(w - k, o); c.lineTo(w - o, k); c.lineTo(w - o, h - o)
            c.lineTo(k, h - o); c.lineTo(o, h - k); c.closePath()
        }
        outline()
        const g = c.createLinearGradient(0, 0, 0, h)
        const bottom = fill2Opacity >= 0 ? fill2 : fill, bottomA = fill2Opacity >= 0 ? fill2Opacity : fillOpacity
        g.addColorStop(0, rgba(fill, fillOpacity * 0.82)); g.addColorStop(1, rgba(bottom, bottomA * 0.82))
        c.fillStyle = g; c.fill()
        const custom = !Qt.colorEqual(stroke, Theme.line)
        const lineColour = custom ? stroke : Theme.accent
        const lineAlpha = custom ? Math.max(0.5, stroke.a) : 0.34
        // Just the hairline (V4: the soft glow round every panel made the whole UI look generated).
        c.strokeStyle = rgba(lineColour, lineAlpha); c.lineWidth = strokeWidth; outline(); c.stroke()
        if (fillOpacity <= 0.01) return
        if (w > 90 && h > 34) {
            // Two quiet brackets, no glow (V4).
            const b = Math.min(9, w / 8, h / 4)
            c.strokeStyle = rgba(Theme.accent, 0.7); c.lineWidth = 1.2
            c.beginPath(); c.moveTo(o, b); c.lineTo(o, o); c.lineTo(b, o); c.stroke()
            c.beginPath(); c.moveTo(w - o, h - b); c.lineTo(w - o, h - o); c.lineTo(w - b, h - o); c.stroke()
            // A tiny mark on each cut corner.
            c.fillStyle = rgba(Theme.accent, 0.7)
            c.fillRect(w - k / 2 - 1, k / 2 - 1, 2, 2); c.fillRect(k / 2 - 1, h - k / 2 - 1, 2, 2)
        }
        if (edgeGlow && w > 40) {
            const inlay = c.createLinearGradient(0, 0, w, 0)
            inlay.addColorStop(0, rgba(glowColour, 0)); inlay.addColorStop(0.35, rgba(glowColour, 0.9))
            inlay.addColorStop(0.65, rgba(glowColour, 0.9)); inlay.addColorStop(1, rgba(glowColour, 0))
            c.strokeStyle = inlay; c.globalAlpha = 0.85; c.lineWidth = 1
            c.beginPath(); c.moveTo(k, o); c.lineTo(w - k - 4, o); c.stroke()
            const wash = c.createLinearGradient(0, 0, 0, Math.min(56, h))
            wash.addColorStop(0, rgba(glowColour, 0.06)); wash.addColorStop(1, rgba(glowColour, 0))
            c.save(); outline(); c.clip(); c.fillStyle = wash; c.fillRect(0, 0, w, Math.min(56, h)); c.restore()
        }
    }
    // V3 lacquer: a crisp small radius, a deep fill with a faint gloss at the top, a brass bevel catching the
    // light along the top edge, a hairline, and (when live) a brass inlay instead of a glow.
    function paintLacquer(c, w, h) {
        const o = strokeWidth / 2, r = Math.min(5, w / 2 - 1, h / 2 - 1)
        function outline() {
            c.beginPath()
            c.moveTo(o + r, o); c.lineTo(w - o - r, o); c.arcTo(w - o, o, w - o, o + r, r)
            c.lineTo(w - o, h - o - r); c.arcTo(w - o, h - o, w - o - r, h - o, r)
            c.lineTo(o + r, h - o); c.arcTo(o, h - o, o, h - o - r, r)
            c.lineTo(o, o + r); c.arcTo(o, o, o + r, o, r)
            c.closePath()
        }
        outline()
        const g = c.createLinearGradient(0, 0, 0, h)
        const bottom = fill2Opacity >= 0 ? fill2 : fill, bottomA = fill2Opacity >= 0 ? fill2Opacity : fillOpacity
        g.addColorStop(0, rgba(Qt.lighter(fill, 1.18), fillOpacity))
        g.addColorStop(Math.min(0.5, 40 / Math.max(h, 1)), rgba(fill, fillOpacity))
        g.addColorStop(1, rgba(bottom, bottomA))
        c.fillStyle = g; c.fill()
        c.strokeStyle = rgba(stroke, stroke.a); c.lineWidth = strokeWidth; c.stroke()
        if (fillOpacity <= 0.01) return
        if (w > 24 && h > 14) {
            // Bevel: light on the top inside edge, a little shade on the bottom one.
            const bevel = c.createLinearGradient(0, 0, w, 0)
            bevel.addColorStop(0, rgba(Theme.accent, 0)); bevel.addColorStop(0.25, rgba(Theme.accent, 0.20))
            bevel.addColorStop(0.75, rgba(Theme.accent, 0.20)); bevel.addColorStop(1, rgba(Theme.accent, 0))
            c.strokeStyle = bevel; c.lineWidth = 1
            c.beginPath(); c.moveTo(r + 1, o + 1.5); c.lineTo(w - r - 1, o + 1.5); c.stroke()
            c.strokeStyle = rgba(Theme.shadeBase, 0.35)
            c.beginPath(); c.moveTo(r + 1, h - o - 1.5); c.lineTo(w - r - 1, h - o - 1.5); c.stroke()
        }
        if (edgeGlow && w > 40) {
            const inlay = c.createLinearGradient(0, 0, w, 0)
            inlay.addColorStop(0, rgba(glowColour, 0)); inlay.addColorStop(0.5, rgba(glowColour, 0.75)); inlay.addColorStop(1, rgba(glowColour, 0))
            c.strokeStyle = inlay; c.lineWidth = 1.2
            c.beginPath(); c.moveTo(r, o); c.lineTo(w - r, o); c.stroke()
            const wash = c.createLinearGradient(0, 0, 0, Math.min(50, h))
            wash.addColorStop(0, rgba(glowColour, 0.045)); wash.addColorStop(1, rgba(glowColour, 0))
            c.save(); outline(); c.clip(); c.fillStyle = wash; c.fillRect(0, 0, w, Math.min(50, h)); c.restore()
        }
        if (brackets) {
            // Engraved register marks in the corners.
            const b = Math.min(7, w / 5, h / 5)
            c.strokeStyle = rgba(bracketColour, 0.55); c.lineWidth = 1
            for (const [x, y, dx, dy] of [[4, 4, 1, 1], [w - 4, 4, -1, 1], [4, h - 4, 1, -1], [w - 4, h - 4, -1, -1]]) {
                c.beginPath(); c.moveTo(x, y + dy * b); c.lineTo(x, y); c.lineTo(x + dx * b, y); c.stroke()
            }
        }
    }
    onPaint: {
        const c = getContext("2d"), w = width, h = height, k = Math.min(cut, w / 3, h / 3), o = strokeWidth / 2
        const glass = Theme.glass, rr = Math.min(cut * 0.85, w / 2 - 1, h / 2 - 1)
        dirtyArt = false; paintedW = Math.round(w); paintedH = Math.round(h)
        c.reset(); c.clearRect(0, 0, w, h)
        if (Theme.holo) { paintHolo(c, w, h); return }
        if (Theme.lacquer) { paintLacquer(c, w, h); return }
        function outline() {
            c.beginPath()
            if (glass) {
                c.moveTo(o + rr, o); c.lineTo(w - o - rr, o); c.arcTo(w - o, o, w - o, o + rr, rr)
                c.lineTo(w - o, h - o - rr); c.arcTo(w - o, h - o, w - o - rr, h - o, rr)
                c.lineTo(o + rr, h - o); c.arcTo(o, h - o, o, h - o - rr, rr)
                c.lineTo(o, o + rr); c.arcTo(o, o, o + rr, o, rr)
            } else {
                c.moveTo(o, o); c.lineTo(w - k, o); c.lineTo(w - o, k); c.lineTo(w - o, h - o)
                c.lineTo(k, h - o); c.lineTo(o, h - k)
            }
            c.closePath()
        }
        outline()
        if (fill2Opacity >= 0) {
            const g = c.createLinearGradient(0, 0, 0, h)
            g.addColorStop(0, rgba(fill, fillOpacity)); g.addColorStop(1, rgba(fill2, fill2Opacity))
            c.fillStyle = g
        } else {
            c.fillStyle = rgba(fill, fillOpacity)
        }
        c.fill()
        c.strokeStyle = rgba(stroke, stroke.a); c.lineWidth = strokeWidth; c.stroke()
        if (edgeGlow && w > 40 && glass) {
            // Glass: a faint sheen along the top edge.
            const g = c.createLinearGradient(0, 0, w, 0)
            g.addColorStop(0, rgba(glowColour, 0)); g.addColorStop(0.3, rgba(glowColour, 0.55))
            g.addColorStop(0.7, rgba(glowColour, 0.55)); g.addColorStop(1, rgba(glowColour, 0))
            c.strokeStyle = g; c.lineWidth = 1
            c.beginPath(); c.moveTo(rr + 2, o); c.lineTo(w - rr - 2, o); c.stroke()
            const v = c.createLinearGradient(0, 0, 0, Math.min(46, h))
            v.addColorStop(0, rgba(glowColour, 0.05)); v.addColorStop(1, rgba(glowColour, 0))
            c.save(); outline(); c.clip(); c.fillStyle = v; c.fillRect(0, 0, w, Math.min(46, h)); c.restore()
        } else if (edgeGlow && w > 40) {
            const g = c.createLinearGradient(0, 0, w - k, 0)
            g.addColorStop(0, rgba(glowColour, 0)); g.addColorStop(0.35, rgba(glowColour, 0.9))
            g.addColorStop(0.65, rgba(glowColour, 0.9)); g.addColorStop(1, rgba(glowColour, 0))
            c.strokeStyle = g
            c.globalAlpha = 0.18; c.lineWidth = 5
            c.beginPath(); c.moveTo(k, o + 1); c.lineTo(w - k - 4, o + 1); c.stroke()
            c.globalAlpha = 1; c.lineWidth = 1.2
            c.beginPath(); c.moveTo(k, o); c.lineTo(w - k - 4, o); c.stroke()
            // Light falling from the edge into the panel.
            const v = c.createLinearGradient(0, 0, 0, Math.min(60, h))
            v.addColorStop(0, rgba(glowColour, 0.07)); v.addColorStop(1, rgba(glowColour, 0))
            c.fillStyle = v
            c.beginPath(); c.moveTo(o, o); c.lineTo(w - k, o); c.lineTo(w - o, k); c.lineTo(w - o, Math.min(60, h)); c.lineTo(o, Math.min(60, h)); c.closePath(); c.fill()
        }
        if (brackets && !glass) {
            const b = Math.min(14, w / 4, h / 4)
            c.strokeStyle = rgba(bracketColour, 0.95); c.lineWidth = 1.6
            c.beginPath(); c.moveTo(o, b); c.lineTo(o, o); c.lineTo(b, o); c.stroke()
            c.beginPath(); c.moveTo(w - o, h - b); c.lineTo(w - o, h - o); c.lineTo(w - b, h - o); c.stroke()
        }
    }
}
