import QtQuick
import "../theme"

// LOCAL AI (APVIS for Windows): which Ollama model answers, whether it runs on the
// graphics card or in light mode (a game is running), and how much graphics memory
// is in use. "Switch" opens the Local AI settings.
GlassCard {
    id: card
    title: "LOCAL AI"
    signal go(string key)
    onOpened: go("settings:ai")
    readonly property var route: shell.route || ({})
    readonly property var ai: (typeof shell.aiStatus !== "undefined" && shell.aiStatus) ? shell.aiStatus : ({})
    readonly property var gpu: (shell.game || {}).gpu || null
    readonly property string model: ai.model || route.model || ""
    readonly property string mode: ai.mode || (route.reachable ? "gpu" : "off")
    live: mode === "light"
    tint: Theme.attention

    Item {
        width: parent.width; height: 52
        Rectangle {
            width: 40; height: 40; radius: 20; anchors.verticalCenter: parent.verticalCenter
            color: "transparent"; border.width: 1.5
            border.color: card.mode === "gpu" ? Theme.accent : card.mode === "light" ? Theme.attention : Theme.muted
            Glyph { anchors.centerIn: parent; width: 20; height: 20; kind: "brain"; stroke: parent.border.color }
        }
        Column {
            x: 54; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 54 - switchButton.width - 10; spacing: 3
            Text { width: parent.width; elide: Text.ElideRight; color: Theme.text; font.pixelSize: 15
                   text: card.model ? card.model : card.route.checking ? "Looking for Ollama…" : "Ollama isn't running" }
            Text { width: parent.width; elide: Text.ElideRight; font.pixelSize: 12
                   color: card.mode === "light" ? Theme.attention : Theme.muted
                   text: card.ai.reason ? card.ai.reason
                         : card.mode === "gpu" ? "On the graphics card · stays on this PC"
                         : card.mode === "light" ? "Light mode while you play"
                         : "Start Ollama to ask questions" }
        }
        HudButton { id: switchButton; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: 78; implicitHeight: 34; caption: card.model ? "Switch" : "Set up"; onClicked: card.go("settings:ai") }
    }
    // Graphics memory: what the model (and anything else) holds on the card right now.
    Item {
        visible: !!card.gpu && !!card.gpu.vramTotal
        width: parent.width; height: 34
        Text { y: 2; text: Theme.label("GRAPHICS MEMORY"); color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1.6 }
        Text { anchors.right: parent.right; y: 0; color: Theme.text; font.pixelSize: 12; font.family: Theme.monoFont
               text: card.gpu ? (card.gpu.vramUsed / 1024).toFixed(1) + " / " + (card.gpu.vramTotal / 1024).toFixed(0) + " GB" : "" }
        Rectangle { anchors.bottom: parent.bottom; anchors.bottomMargin: 4; width: parent.width; height: 3; radius: 1.5; color: Theme.line
            Rectangle { height: parent.height; radius: 1.5; color: Theme.accent
                        width: card.gpu && card.gpu.vramTotal ? parent.width * Math.min(1, card.gpu.vramUsed / card.gpu.vramTotal) : 0
                        Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } } } }
    }
}
