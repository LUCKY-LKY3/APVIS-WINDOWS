import QtQuick

// A live history graph: filled area, glowing line, scale grid, latest-value dot.
// `values` are real samples; nothing is drawn until at least two exist.
Canvas {
    id: spark
    property var values: []
    property var second: []               // optional second series (e.g. upload)
    property real maxValue: 0             // 0 = auto-scale
    property color colour: Theme.accent
    property color colour2: Theme.warm
    implicitHeight: 48
    onValuesChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
    onPaint: {
        const c = getContext("2d"), w = width, h = height
        c.reset(); c.clearRect(0, 0, w, h)
        c.strokeStyle = rgba(Theme.accent, 0.08); c.lineWidth = 1
        for (let i = 1; i < 4; ++i) { c.beginPath(); c.moveTo(0, Math.round(h * i / 4) + .5); c.lineTo(w, Math.round(h * i / 4) + .5); c.stroke() }
        for (let x = 0; x < w; x += 24) { c.beginPath(); c.moveTo(x + .5, 0); c.lineTo(x + .5, h); c.stroke() }
        const all = values.concat(second || [])
        if (values.length < 2) return
        const top = maxValue > 0 ? maxValue : Math.max(1, Math.max.apply(null, all) * 1.15)
        function draw(series, col, fill) {
            if (!series || series.length < 2) return
            const n = series.length, step = w / Math.max(1, n - 1)
            c.beginPath()
            for (let i = 0; i < n; ++i) { const x = i * step, y = h - 2 - (h - 4) * Math.min(1, series[i] / top); i ? c.lineTo(x, y) : c.moveTo(x, y) }
            if (fill) {
                c.save(); c.lineTo(w, h); c.lineTo(0, h); c.closePath()
                const g = c.createLinearGradient(0, 0, 0, h)
                g.addColorStop(0, rgba(col, 0.28)); g.addColorStop(1, rgba(col, 0.0))
                c.fillStyle = g; c.fill(); c.restore()
                c.beginPath()
                for (let i = 0; i < n; ++i) { const x = i * step, y = h - 2 - (h - 4) * Math.min(1, series[i] / top); i ? c.lineTo(x, y) : c.moveTo(x, y) }
            }
            c.strokeStyle = rgba(col, 0.25); c.lineWidth = 4; c.stroke()
            c.strokeStyle = rgba(col, 0.95); c.lineWidth = 1.3; c.stroke()
            const ly = h - 2 - (h - 4) * Math.min(1, series[n - 1] / top)
            c.fillStyle = rgba(Theme.text, 1); c.beginPath(); c.arc(w - 1.5, ly, 2.2, 0, Math.PI * 2); c.fill()
        }
        draw(values, colour, true)
        draw(second, colour2, false)
    }
}
