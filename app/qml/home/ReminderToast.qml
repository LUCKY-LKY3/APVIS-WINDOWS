import QtQuick
import QtQuick.Controls
import "../theme"

// A reminder or timer that just came due: slides in at the top, stays until dismissed
// (or 60 s), and several stack into one card. The desktop notification fires as well.
Item {
    id: toast
    property var items: []                      // [{text, kind, at}]
    function add(text, kind) {
        items = items.concat([{ text: text, kind: kind, at: new Date() }]).slice(-4)
        hideTimer.restart()
    }
    function clear() { items = [] }
    readonly property bool shown: items.length > 0
    width: 460; height: col.height + 28
    opacity: shown ? 1 : 0
    visible: opacity > 0.01
    transform: Translate { y: toast.shown ? 0 : -24; Behavior on y { NumberAnimation { duration: 380; easing.type: Easing.OutCubic } } }
    Behavior on opacity { NumberAnimation { duration: 300 } }
    Timer { id: hideTimer; interval: 60000; onTriggered: toast.clear() }

    Chamfer { anchors.fill: parent; cut: 12; fill: Theme.panel; fillOpacity: 0.96; fill2: Theme.bgBottom; fill2Opacity: 0.9
              stroke: Theme.accent; edgeGlow: true }
    Column {
        id: col
        x: 18; y: 14; width: parent.width - 36; spacing: 8
        Row {
            spacing: 10
            Glyph { width: 18; height: 18; kind: "timer"; stroke: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
            Text { text: toast.items.length > 1 ? toast.items.length + " REMINDERS" : (toast.items[0] || {}).kind === "timer" ? Theme.label("TIMER") : Theme.label("REMINDER")
                   color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 11; font.letterSpacing: Theme.caps ? 2 : 0.3; font.bold: true
                   anchors.verticalCenter: parent.verticalCenter }
        }
        Repeater {
            model: toast.items
            delegate: Text {
                required property var modelData
                width: col.width; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 16
                text: modelData.text + "  ·  " + Qt.formatTime(modelData.at, "HH:mm")
            }
        }
        HudButton { width: 120; implicitHeight: 32; caption: "Dismiss"; onClicked: toast.clear() }
    }
    Accessible.role: Accessible.AlertMessage
    Accessible.name: toast.items.map(i => i.text).join(". ")
}
