import QtQuick
import QtQuick.Controls
import "../theme"

// Left navigation (owner concept): pages and the two everyday apps. The
// selection light slides between items; dots mark things that need you.
Item {
    id: rail
    property string current: ""                 // "" = Home
    property var badges: ({})                   // key -> true when something waits there
    signal navigate(string key)
    readonly property var items: [
        ["", "Home", "home"], ["files", "Files", "files"], ["apps", "Apps", "apps"],
        ["system", "System", "chip"], ["devices", "Devices", "device"], ["atlas", "Intelligence", "brain"],
        ["missions", "Automation", "gear"], ["notes", "Memory", "memory"], ["settings", "Settings", "settings"]
    ].concat(shell.developerMode ? [["dev", "Developer", "terminal"]] : [])
    property Item chosen: null
    implicitHeight: col.height
    implicitWidth: 190

    Rectangle {
        id: light
        visible: rail.chosen !== null
        x: 0; width: rail.width; height: 44; radius: 9
        y: rail.chosen ? rail.chosen.y : 0
        color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, Theme.lacquer ? 0.05 : 0.09)
        border.width: Theme.lacquer && !Theme.holo ? 0 : 1; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.22)
        Behavior on y { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }
        Rectangle { x: -1; y: Theme.lacquer ? 12 : 10; width: Theme.lacquer ? 2 : 3; height: parent.height - (Theme.lacquer ? 24 : 20); radius: 1.5; color: Theme.accent }
        Rectangle { visible: !Theme.lacquer || Theme.holo; x: -4; y: 6; width: 9; height: parent.height - 12; radius: 4.5; color: Theme.accent; opacity: 0.18 }
    }
    Column {
        id: col
        width: parent.width
        spacing: 2
        Repeater {
            model: rail.items
            delegate: AbstractButton {
                id: navItem
                required property var modelData
                readonly property bool active: rail.current === modelData[0]
                width: col.width; height: 44
                onActiveChanged: if (active) rail.chosen = navItem
                Component.onCompleted: if (active) rail.chosen = navItem
                Accessible.name: modelData[1]
                onClicked: rail.navigate(modelData[0])
                background: Rectangle {
                    radius: 9
                    color: navItem.hovered && !navItem.active ? Qt.rgba(Theme.hover.r, Theme.hover.g, Theme.hover.b, 0.7) : "transparent"
                    border.width: navItem.visualFocus ? 1.5 : 0; border.color: Theme.text
                    Behavior on color { ColorAnimation { duration: 150 } }
                }
                contentItem: Item {
                    Glyph { x: 14; anchors.verticalCenter: parent.verticalCenter; width: 19; height: 19; kind: navItem.modelData[2]
                            stroke: navItem.active ? Theme.accent : navItem.hovered ? Theme.text : Theme.muted }
                    Text { x: 46; anchors.verticalCenter: parent.verticalCenter; text: navItem.modelData[1]
                           color: navItem.active ? (Theme.lacquer ? Qt.lighter(Theme.accent, 1.35) : Theme.text)
                                  : navItem.hovered ? Theme.text : Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, 0.78)
                           font.pixelSize: 15
                           Behavior on color { ColorAnimation { duration: 150 } } }
                    Rectangle {
                        visible: !!rail.badges[navItem.modelData[0]]
                        anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                        width: 7; height: 7; radius: 3.5; color: Theme.attention
                    }
                }
            }
        }
    }
}
