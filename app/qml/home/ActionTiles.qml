import QtQuick
import QtQuick.Controls
import "../theme"

// The six action tiles under the core (owner concept). Each does something
// real: Ask, Search, Create (a new note), Automate (Missions), Analyse (a
// measured system check), More (all apps).
Row {
    id: tiles
    property real tileWidth: 118
    property real tileHeight: 88
    property int order: 0
    property bool shown: true
    signal chosen(string key)
    spacing: 14
    Repeater {
        model: [["ask", "Ask", "ask"], ["search", "Search", "search"], ["create", "Create", "plus"],
                ["automate", "Automate", "gear"], ["analyse", "Analyse", "chart"], ["more", "More", "grid"]]
        delegate: AbstractButton {
            id: tile
            required property var modelData
            required property int index
            width: tiles.tileWidth; height: tiles.tileHeight
            Accessible.name: modelData[1]
            onClicked: tiles.chosen(modelData[0])
            opacity: 0
            transform: Translate { id: lift; y: tile.hovered ? -3 : 0; Behavior on y { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } } }
            scale: pressed ? 0.96 : 1
            Behavior on scale { NumberAnimation { duration: 90 } }
            states: State { name: "on"; when: tiles.shown; PropertyChanges { target: tile; opacity: 1 } }
            transitions: Transition { to: "on"; SequentialAnimation {
                PauseAnimation { duration: 60 * tile.index + 90 * tiles.order }
                NumberAnimation { property: "opacity"; duration: 380; easing.type: Easing.OutCubic } } }
            background: Item {
                Chamfer { anchors.fill: parent; cut: 12; fill: Theme.panel; fillOpacity: 0.78; fill2: Theme.bgBottom; fill2Opacity: 0.85
                          stroke: tile.hovered || tile.visualFocus ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7)
                                                                 : Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 1)
                          edgeGlow: tile.hovered }
                Rectangle { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 1
                            width: parent.width * 0.5; height: 2; radius: 1; color: Theme.accent
                            opacity: tile.hovered || tile.visualFocus ? 0.9 : 0
                            Behavior on opacity { NumberAnimation { duration: 150 } } }
            }
            contentItem: Item {
                Glyph { anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.2; width: 24; height: 24; kind: tile.modelData[2]
                        stroke: tile.hovered ? Theme.accent : Theme.text }
                Text { anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.62; text: tile.modelData[1]
                       color: Theme.text; font.pixelSize: 14 }
            }
        }
    }
}
