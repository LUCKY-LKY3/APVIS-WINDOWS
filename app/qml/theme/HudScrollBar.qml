import QtQuick
import QtQuick.Controls

// Thin emerald scroll bar: quiet until you scroll or hover, then brighter.
ScrollBar {
    id: bar
    implicitWidth: 8
    padding: 2
    // Nothing to scroll: no bar (some styles still draw a full-length handle).
    visible: size < 1.0
    contentItem: Rectangle {
        implicitWidth: 4
        radius: 2
        color: bar.pressed ? Theme.text : Theme.accent
        opacity: bar.policy === ScrollBar.AlwaysOn || bar.active || bar.hovered ? 0.85 : 0.28
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }
    background: Item {}
}
