import QtQuick
import "../theme"

// INTELLIGENCE ROUTE (owner concept): which local model answers, and that it
// stays on this computer or home network. "Switch" opens the Local AI settings.
GlassCard {
    id: card
    title: "INTELLIGENCE ROUTE"
    signal go(string key)
    onOpened: go("settings:ai")
    readonly property var route: shell.route || ({})
    // The gaming PC answers while it is on (Settings → Local AI → Gaming PC boost).
    readonly property var boost: (shell.settings || {}).boost || ({})
    readonly property bool pc: !!boost.enabled && boost.reachable === true && !!boost.fast
    Item {
        width: parent.width; height: 56
        Glyph { anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; kind: "brain"
                stroke: card.route.reachable || card.pc ? Theme.accent : Theme.muted }
        Column {
            x: 58; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 58 - switchButton.width - 10; spacing: 3
            Text { width: parent.width; elide: Text.ElideRight; color: Theme.text; font.pixelSize: 14
                   text: card.pc ? "Gaming PC: " + card.boost.fast :
                         card.route.reachable ? "Local model: " + (card.route.model || "none installed") :
                         card.route.checking ? "Looking for local AI…" : "Local AI not reachable" }
            Text { width: parent.width; elide: Text.ElideRight; color: Theme.muted; font.pixelSize: 12
                   text: card.pc ? "Privacy: home network  ·  this computer takes over when it's off" :
                         "Privacy: Local only" + (card.route.version ? "  ·  Ollama " + card.route.version : "") }
        }
        HudButton { id: switchButton; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    width: 78; implicitHeight: 34; caption: card.route.reachable ? "Switch" : "Set up"; onClicked: card.go("settings:ai") }
    }
}
