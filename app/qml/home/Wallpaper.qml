import QtQuick
import "../theme"

// The background (owner concept): black, with faint green smoke drifting in
// from the edges and pooling behind the core. One pre-rendered image
// (qml/art/nebula.png) and a vignette; nothing here animates.
Item {
    id: wall
    property point centre: Qt.point(0.5, 0.43)    // where the core sits (0..1)
    Rectangle { anchors.fill: parent; color: Theme.ink }
    Image {
        anchors.fill: parent
        source: (Theme.artDir ? Theme.artDir : "../art/") + Theme.wallpaper
        fillMode: Image.PreserveAspectCrop
        smooth: true
        opacity: 0.95
    }
    // Vignette so cards and edges sit on near-black.
    Canvas {
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            const c = getContext("2d"), w = width, h = height
            c.reset()
            const cx = w * wall.centre.x, cy = h * wall.centre.y
            const g = c.createRadialGradient(cx, cy, Math.min(w, h) * 0.2, cx, cy, Math.max(w, h) * 0.75)
            g.addColorStop(0, Theme.css(Theme.shadeBase, 0)); g.addColorStop(0.7, Theme.css(Theme.shadeBase, 0.35)); g.addColorStop(1, Theme.css(Theme.shadeBase, 0.7))
            c.fillStyle = g; c.fillRect(0, 0, w, h)
        }
    }
}
