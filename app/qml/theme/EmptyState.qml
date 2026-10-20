import QtQuick

// An empty list, shown properly: a slowly turning HUD emblem around a glyph,
// a title, a hint, and example chips that fill in the Ask bar.
Item {
    id: empty
    property string glyph: "core"
    property string title: ""
    property string hint: ""
    property var suggestions: []
    property real emblemSize: 170
    signal suggested(string text)
    readonly property bool still: !!(shell.render || {}).reducedMotion || !!(shell.render || {}).lite
    // The rings turn for a few seconds when the empty state appears, then rest: a ring that never stops
    // makes the whole screen redraw 60 times a second on a page nobody is touching (3.0.8, measured on
    // the OptiPlex: ~85 ms/s UI + 60 ms/s GPU on the Apps page while still).
    property bool resting: false
    onVisibleChanged: { resting = false; if (visible) rest.restart() }
    Timer { id: rest; interval: 9000; running: empty.visible; onTriggered: empty.resting = true }
    implicitWidth: 520
    implicitHeight: col.implicitHeight

    Column {
        id: col
        width: parent.width
        spacing: 14
        Item {
            id: emblem
            width: empty.emblemSize; height: width; anchors.horizontalCenter: parent.horizontalCenter
            // Soft core light.
            Canvas {
                anchors.fill: parent
                Component.onCompleted: requestPaint()
                function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
                onPaint: {
                    const c = getContext("2d"), r = width / 2
                    c.reset()
                    const g = c.createRadialGradient(r, r, 0, r, r, r)
                    g.addColorStop(0, rgba(Theme.accent, 0.20)); g.addColorStop(0.45, rgba(Theme.accent, 0.06)); g.addColorStop(1, rgba(Theme.accent, 0))
                    c.fillStyle = g; c.fillRect(0, 0, width, height)
                }
            }
            // Outer ring: ticks + two bright arcs (turns slowly).
            Canvas {
                anchors.fill: parent
                Component.onCompleted: requestPaint()
                function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
                onPaint: {
                    const c = getContext("2d"), cx = width / 2, r = width / 2 - 6
                    c.reset()
                    for (let i = 0; i < 72; ++i) {
                        const a = i / 72 * Math.PI * 2, major = i % 6 === 0
                        c.strokeStyle = rgba(Theme.accent, major ? 0.6 : 0.22); c.lineWidth = major ? 1.3 : 0.8
                        c.beginPath(); c.moveTo(cx + Math.cos(a) * r, cx + Math.sin(a) * r)
                        c.lineTo(cx + Math.cos(a) * (r - (major ? 8 : 4)), cx + Math.sin(a) * (r - (major ? 8 : 4))); c.stroke()
                    }
                    c.strokeStyle = rgba(Theme.accent, 0.9); c.lineWidth = 2
                    c.beginPath(); c.arc(cx, cx, r + 3, -0.4, 0.5); c.stroke()
                    c.beginPath(); c.arc(cx, cx, r + 3, Math.PI - 0.4, Math.PI + 0.5); c.stroke()
                }
                RotationAnimation on rotation { from: 0; to: 360; duration: 40000; loops: Animation.Infinite; running: empty.visible && !empty.still && !empty.resting }
            }
            // Inner dashed ring (turns the other way).
            Canvas {
                anchors.centerIn: parent; width: parent.width * 0.64; height: width
                Component.onCompleted: requestPaint()
                function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
                onPaint: {
                    const c = getContext("2d"), cx = width / 2, r = width / 2 - 2
                    c.reset(); c.lineWidth = 1.2
                    for (let i = 0; i < 24; ++i) {
                        const a = i / 24 * Math.PI * 2
                        c.strokeStyle = rgba(Theme.text, i % 3 === 0 ? 0.55 : 0.2)
                        c.beginPath(); c.arc(cx, cx, r, a, a + 0.14); c.stroke()
                    }
                }
                RotationAnimation on rotation { from: 360; to: 0; duration: 26000; loops: Animation.Infinite; running: empty.visible && !empty.still && !empty.resting }
            }
            Rectangle { anchors.centerIn: parent; width: parent.width * 0.36; height: width; radius: width / 2
                        color: Qt.rgba(Theme.bgBottom.r, Theme.bgBottom.g, Theme.bgBottom.b, 0.85)
                        border.width: 1; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.6) }
            Glyph { anchors.centerIn: parent; width: parent.width * 0.17; height: width; kind: empty.glyph; stroke: Theme.accent }
        }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: empty.title; color: Theme.text; font.pixelSize: 18; font.letterSpacing: 1.5 }
        Text { anchors.horizontalCenter: parent.horizontalCenter; width: Math.min(parent.width, 480); horizontalAlignment: Text.AlignHCenter
               text: empty.hint; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap; lineHeight: 1.2 }
        Row {
            visible: empty.suggestions.length > 0
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 8
            Repeater {
                model: empty.suggestions
                delegate: HudButton {
                    required property var modelData
                    implicitHeight: 32; caption: "“" + modelData + "”"; glyph: "ask"
                    onClicked: empty.suggested(modelData)
                }
            }
        }
    }
}
