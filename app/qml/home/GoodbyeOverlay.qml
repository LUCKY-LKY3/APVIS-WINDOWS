import QtQuick
import "../theme"

// Shutdown (owner concept, screen 15): after the owner confirms, a calm
// goodbye screen shows, then the real power action runs. If the system
// refuses (or after waking from sleep) the screen goes away again.
Item {
    id: bye
    property string action: ""                  // suspend | reboot | poweroff | logout
    readonly property bool active: action !== ""
    signal proceed(string action)
    visible: active || opacity > 0.01
    opacity: active ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 450; easing.type: Easing.InOutCubic } }
    readonly property string word: action === "reboot" ? "Restarting…" : action === "suspend" ? "Going to sleep…" :
                                   action === "logout" ? "Logging out…" : "Shutting down…"
    property real t: 0
    function start(a) { action = a; t = 0; run.restart() }
    SequentialAnimation {
        id: run
        NumberAnimation { target: bye; property: "t"; from: 0; to: 1; duration: 1500; easing.type: Easing.InOutQuad }
        ScriptAction { script: bye.proceed(bye.action) }
        PauseAnimation { duration: bye.action === "suspend" ? 2500 : 8000 }
        ScriptAction { script: bye.action = "" }       // still here: sleep ended, or the system said no
    }

    Rectangle { anchors.fill: parent; color: Theme.ink }
    MouseArea { anchors.fill: parent; enabled: bye.active }
    Image {
        anchors.fill: parent; source: (Theme.artDir ? Theme.artDir : "../art/") + Theme.wallpaper; fillMode: Image.PreserveAspectCrop; opacity: Theme.lacquer ? 0.9 : 0.35
    }
    Column {
        anchors.centerIn: parent; spacing: 18
        ApvisMark { anchors.horizontalCenter: parent.horizontalCenter; width: 96; height: 84; glow: 1.0 - 0.6 * bye.t }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: Theme.label("APVIS OS"); color: Theme.text
               font.pixelSize: 26; font.weight: Font.Light; font.letterSpacing: 9; leftPadding: 9 }
        Item { width: 1; height: 8 }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: bye.word; color: Theme.text; font.pixelSize: 15 }
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter; width: 260; height: 3; radius: 1.5; color: Theme.sheen(0.08)
            Rectangle { height: parent.height; radius: 1.5; width: parent.width * bye.t; color: Theme.accent }
        }
        Item { width: 1; height: 14 }

    }

}
