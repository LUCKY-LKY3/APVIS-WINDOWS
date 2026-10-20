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
    property bool app: false                     // APVIS for Windows: the app's own six
    signal chosen(string key)
    spacing: app ? 10 : 14
    Repeater {
        model: tiles.app
            ? [["brief", "Brief me", "activity"], ["web", "Web", "search"], ["page:atlas", "World", "brain"],
               ["page:game", "Game", "game"], ["page:notes", "Memory", "memory"], ["page:system", "System", "chip"]]
            : [["ask", "Ask", "ask"], ["search", "Search", "search"], ["create", "Create", "plus"],
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
                Rectangle { visible: tiles.app; anchors.fill: parent; radius: height / 2
                            color: tile.hovered ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.14) : Qt.rgba(Theme.panel.r, Theme.panel.g, Theme.panel.b, 0.8)
                            border.width: 1; border.color: tile.hovered || tile.visualFocus ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7) : Theme.line
                            Behavior on color { ColorAnimation { duration: 150 } } }
                Chamfer { visible: !tiles.app; anchors.fill: parent; cut: 12; fill: Theme.panel; fillOpacity: 0.78; fill2: Theme.bgBottom; fill2Opacity: 0.85
                          stroke: tile.hovered || tile.visualFocus ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7)
                                                                 : Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 1)
                          edgeGlow: tile.hovered }
                Rectangle { visible: !tiles.app; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 1
                            width: parent.width * 0.5; height: 2; radius: 1; color: Theme.accent
                            opacity: tile.hovered || tile.visualFocus ? 0.9 : 0
                            Behavior on opacity { NumberAnimation { duration: 150 } } }
            }
            contentItem: Item {
                Glyph { visible: !tiles.app; anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.2; width: 24; height: 24; kind: tile.modelData[2]
                        stroke: tile.hovered ? Theme.accent : Theme.text }
                Text { visible: !tiles.app; anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.62; text: tile.modelData[1]
                       color: Theme.text; font.pixelSize: 14 }
                Row {
                    visible: tiles.app
                    anchors.centerIn: parent; spacing: 9
                    Glyph { anchors.verticalCenter: parent.verticalCenter; width: 17; height: 17; kind: tile.modelData[2]
                            stroke: tile.hovered ? Theme.accent : Qt.lighter(Theme.accent, 1.25) }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: tile.modelData[1]; color: Theme.text; font.pixelSize: 13 }
                }
            }
        }
    }
}
