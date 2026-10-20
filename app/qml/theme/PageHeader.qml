import QtQuick

// Page title block: a section code ("// 02"), a large spaced title, a subtitle,
// and an underline that draws in with a bright scan head when the page opens.
// Buttons placed inside sit on the right.
Item {
    id: head
    property string code: ""
    property string title: ""
    property string subtitle: ""
    property real reveal: 1
    default property alias actions: actionRow.data
    implicitHeight: sub.y + sub.implicitHeight + 16
    height: implicitHeight

    Row {
        id: titleRow
        spacing: 12
        opacity: head.reveal
        transform: Translate { x: (1 - head.reveal) * -16 }
        Text { visible: head.code.length > 0 && !Theme.lacquer; text: "//" + head.code; color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 12
               font.letterSpacing: 1.5; anchors.baseline: bigTitle.baseline }
        Text { id: bigTitle; text: Theme.label(head.title); color: Theme.text; font.pixelSize: Theme.lacquer ? 32 : 28
               font.weight: Theme.lacquer ? Font.Normal : Font.Light
               font.letterSpacing: Theme.caps ? 6 : 0.5; font.family: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family }
    }
    Text {
        id: sub
        anchors.top: titleRow.bottom; anchors.topMargin: 3
        width: parent.width - actionRow.width - 24; wrapMode: Text.WordWrap
        text: head.subtitle; color: Theme.muted; font.pixelSize: 12; lineHeight: 1.15
        opacity: head.reveal
    }
    Row {
        id: actionRow
        anchors.right: parent.right; anchors.top: parent.top; anchors.topMargin: 4
        spacing: 8
        opacity: head.reveal
    }
    // Underline + scan head.
    Item {
        anchors.bottom: parent.bottom; width: parent.width; height: 3
        Rectangle {
            y: 1; height: 1; width: parent.width * head.reveal
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.lacquer ? Theme.line : Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7) }
                GradientStop { position: 0.35; color: Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 0.9) }
                GradientStop { position: 1; color: Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 0.1) } }
        }
        Rectangle { y: Theme.lacquer ? 1 : 0; height: Theme.lacquer ? 1.2 : 3; width: Theme.lacquer ? 40 : 60; color: Theme.accent }
        Rectangle {
            visible: head.reveal < 1 && !Theme.lacquer
            x: parent.width * head.reveal - width; y: -2; height: 7; width: 90; radius: 3.5
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 1; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.8) } }
        }
    }
}
