import QtQuick
import QtQuick.Controls
import "../theme"

// The lock screen (owner concept, screen 03): time, "Welcome back", your
// password, and power buttons. The password is checked by the system
// (apvis_os.lockscreen → unix_chkpwd); APVIS never keeps it.
Item {
    id: lock
    property bool locked: false
    property date now: new Date()
    property bool checking: false
    property string message: ""
    readonly property var host: shell.host || ({})
    signal unlocked()
    visible: locked || opacity > 0.01
    opacity: locked ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 500; easing.type: Easing.InOutCubic } }
    function engage() { message = ""; field.text = ""; locked = true; Qt.callLater(() => field.forceActiveFocus()) }
    function submit() { if (checking || !field.text) return; checking = true; message = ""; shell.unlock(field.text); field.text = "" }
    Connections {
        target: shell
        function onUnlockResult(ok, text) {
            lock.checking = false
            if (ok) { lock.locked = false; lock.unlocked() }
            else { lock.message = text; shake.restart(); field.forceActiveFocus() }
        }
    }

    Rectangle { anchors.fill: parent; color: Theme.ink }
    MouseArea { anchors.fill: parent; enabled: lock.locked; onClicked: field.forceActiveFocus() }
    Image { anchors.fill: parent; source: (Theme.artDir ? Theme.artDir : "../art/") + Theme.wallpaper; fillMode: Image.PreserveAspectCrop; opacity: 0.7 }
    Rectangle { anchors.fill: parent; gradient: Gradient {
        GradientStop { position: 0; color: Theme.shade(0.35) } GradientStop { position: 1; color: Theme.shade(0.75) } } }

    Column {
        anchors.right: parent.right; anchors.rightMargin: 60; y: 50
        Text { anchors.right: parent.right; text: Qt.formatDateTime(lock.now, "HH:mm"); color: Theme.text; font.pixelSize: 64; font.weight: Font.Light }
        Text { anchors.right: parent.right; text: Qt.formatDateTime(lock.now, "dddd d MMMM"); color: Theme.muted; font.pixelSize: 16 }
    }

    Column {
        id: box
        anchors.centerIn: parent
        spacing: 18
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 20
            Rectangle {
                width: 64; height: 64; radius: 32; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12)
                border.width: 1.5; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7)
                anchors.verticalCenter: parent.verticalCenter
                Text { anchors.centerIn: parent; text: (lock.host.name || lock.host.user || "A").slice(0, 1).toUpperCase()
                       color: Theme.text; font.pixelSize: 28; font.weight: Font.Light }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text { text: "Welcome back,"; color: Theme.text; font.pixelSize: 17 }
                Text { text: (lock.host.name || lock.host.user || "") + "."; color: Theme.text; font.pixelSize: 34; font.weight: Font.Light }
            }
        }
        Item {
            id: fieldBox
            anchors.horizontalCenter: parent.horizontalCenter
            width: 380; height: 46
            transform: Translate { id: shakeX }
            SequentialAnimation {
                id: shake
                NumberAnimation { target: shakeX; property: "x"; to: -10; duration: 50 }
                NumberAnimation { target: shakeX; property: "x"; to: 10; duration: 70 }
                NumberAnimation { target: shakeX; property: "x"; to: -6; duration: 60 }
                NumberAnimation { target: shakeX; property: "x"; to: 0; duration: 60 }
            }
            Chamfer { anchors.fill: parent; cut: 12; fill: Theme.panel; fillOpacity: 0.85
                      stroke: field.activeFocus ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.8) : Theme.line }
            TextField {
                id: field
                x: 14; width: parent.width - 64; height: parent.height
                echoMode: TextInput.Password; passwordCharacter: "•"
                placeholderText: lock.checking ? "Checking…" : "Enter password"
                color: Theme.text; placeholderTextColor: Theme.muted; font.pixelSize: 15
                verticalAlignment: TextInput.AlignVCenter; enabled: !lock.checking
                background: Item {}
                Accessible.name: "Password"
                onAccepted: lock.submit()
            }
            Button {
                id: go
                anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                width: 36; height: 34
                Accessible.name: "Unlock"
                onClicked: lock.submit()
                contentItem: Text { text: "→"; color: Theme.text; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 8; color: go.hovered ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.25) : "transparent" }
            }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            height: 18; text: lock.message; color: Theme.attention; font.pixelSize: 13
        }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 60
        spacing: 44
        Repeater {
            model: [["poweroff", "Shut down", "power"], ["reboot", "Restart", "restart"], ["suspend", "Sleep", "moon"]]
            delegate: AbstractButton {
                id: pb
                required property var modelData
                property bool armed: false
                width: 90; height: 64
                Accessible.name: armed ? "Confirm " + modelData[1] : modelData[1]
                Timer { id: disarm; interval: 4000; onTriggered: pb.armed = false }
                onClicked: { if (armed) { armed = false; shell.requestPower(modelData[0]) } else { armed = true; disarm.restart() } }
                contentItem: Column {
                    spacing: 8
                    Glyph { anchors.horizontalCenter: parent.horizontalCenter; width: 22; height: 22; kind: pb.modelData[2]
                            stroke: pb.armed ? Theme.attention : pb.hovered ? Theme.accent : Theme.text }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: pb.armed ? "Press again" : pb.modelData[1]
                           color: pb.armed ? Theme.attention : Theme.muted; font.pixelSize: 12 }
                }
                background: Item {}
            }
        }
    }
}
