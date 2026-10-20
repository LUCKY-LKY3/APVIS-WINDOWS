import QtQuick
import QtQuick.Controls

// An on/off switch with a caption and optional explanation. `on` is bound to
// real state by the page; clicking emits clicked() and the page asks the
// system, so the switch only moves once the change is confirmed.
AbstractButton {
    id: t
    property bool on: false
    property string caption: ""
    property string detail: ""
    property bool busy: false
    implicitWidth: 320
    implicitHeight: Math.max(40, textCol.implicitHeight + 12)
    Accessible.role: Accessible.CheckBox
    Accessible.checkable: true
    Accessible.checked: on
    Accessible.name: caption

    background: Rectangle {
        radius: 6
        color: t.hovered ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.05) : "transparent"
        border.width: t.visualFocus ? 1.5 : 0; border.color: Theme.text
        Behavior on color { ColorAnimation { duration: 150 } }
    }
    contentItem: Item {
        Item {
            id: track
            width: 46; height: 24; anchors.verticalCenter: parent.verticalCenter; x: 4
            Rectangle {
                anchors.fill: parent; radius: 12
                color: t.on ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.22) : Theme.raised
                border.width: 1; border.color: t.on ? Theme.accent : Theme.line
                Behavior on color { ColorAnimation { duration: 200 } }
                Behavior on border.color { ColorAnimation { duration: 200 } }
            }
            // Knob glow + knob.
            Rectangle {
                width: 26; height: 26; radius: 13; anchors.verticalCenter: parent.verticalCenter
                x: knob.x - 5; color: Theme.accent; opacity: t.on ? 0.22 : 0
                Behavior on opacity { NumberAnimation { duration: 200 } }
            }
            Rectangle {
                id: knob
                width: 16; height: 16; radius: 8; anchors.verticalCenter: parent.verticalCenter
                x: t.on ? parent.width - width - 4 : 4
                color: t.on ? Theme.accent : Theme.muted
                opacity: t.busy ? 0.5 : 1
                Behavior on x { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                Behavior on color { ColorAnimation { duration: 200 } }
            }
        }
        Column {
            id: textCol
            x: track.x + track.width + 14; anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x - 6; spacing: 2
            Row {
                spacing: 8
                Text { id: cap; text: t.caption; color: Theme.text; font.pixelSize: 13 }
                Text { text: t.busy ? "…" : t.on ? "ON" : Theme.label("OFF"); color: t.on ? Theme.accent : Theme.muted
                       font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 1.4 : 0.3; anchors.baseline: cap.baseline }
            }
            Text { visible: t.detail.length > 0; width: parent.width; text: t.detail; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.WordWrap }
        }
    }
}
