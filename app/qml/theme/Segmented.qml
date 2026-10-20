import QtQuick
import QtQuick.Controls

// A segmented picker: one glowing highlight slides to the chosen option.
// `options` are values; `label(value)` turns one into text.
Item {
    id: seg
    property var options: []
    property var value
    property var label: v => String(v)
    property bool fill: false            // options share the full width
    signal picked(var value)
    property Item chosen: null
    implicitHeight: 34
    implicitWidth: row.width + 8

    Chamfer { anchors.fill: parent; cut: 8; fill: Theme.bgBottom; fillOpacity: 0.55; stroke: Theme.line }
    Rectangle {
        visible: seg.chosen !== null
        x: row.x + (seg.chosen ? seg.chosen.x : 0); y: 4; height: parent.height - 8
        width: seg.chosen ? seg.chosen.width : 0
        radius: 3
        color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.16)
        border.width: 1; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7)
        Behavior on x { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
        Behavior on width { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
        Rectangle { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; width: parent.width * 0.5; height: 2; color: Theme.accent }
    }
    Row {
        id: row
        x: 4; height: parent.height
        Repeater {
            model: seg.options
            delegate: AbstractButton {
                id: opt
                required property var modelData
                readonly property bool sel: modelData === seg.value
                onSelChanged: if (sel) seg.chosen = opt
                Component.onCompleted: if (sel) seg.chosen = opt
                width: seg.fill ? (seg.width - 8) / Math.max(1, seg.options.length) : txt.implicitWidth + 26; height: row.height
                Accessible.role: Accessible.RadioButton
                Accessible.checked: sel
                Accessible.name: seg.label(modelData)
                onClicked: seg.picked(modelData)
                contentItem: Item {
                    Text { id: txt; anchors.centerIn: parent; text: seg.label(opt.modelData)
                           color: opt.sel ? Theme.text : opt.hovered ? Theme.text : Theme.muted; font.pixelSize: 12
                           Behavior on color { ColorAnimation { duration: 150 } } }
                }
                background: Rectangle { color: "transparent"; border.width: opt.visualFocus ? 1.5 : 0; border.color: Theme.text; radius: 3 }
            }
        }
    }
}
