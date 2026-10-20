import QtQuick

// A glass HUD panel: gradient body, lit top edge, accent corner brackets and a
// header (glyph badge, title, optional meta on the right). Children go in a
// padded column. `reveal` (0..1) + `order` give a staggered rise-in entry.
Item {
    id: panel
    property string title: ""
    property string glyph: ""
    property string meta: ""
    property color metaColour: Theme.muted
    property color tint: Theme.accent
    property bool highlighted: false
    property int order: 0
    property real reveal: 1
    property real padding: 16
    property real spacing: 10
    readonly property real headerHeight: title.length > 0 ? 46 : 0
    default property alias content: column.data
    implicitHeight: column.y + column.implicitHeight + padding + 2
    height: implicitHeight

    readonly property real local: Math.max(0, Math.min(1, reveal * 1.7 - order * 0.1))
    opacity: local
    transform: Translate { y: (1 - panel.local) * 20 }

    Chamfer {
        anchors.fill: parent; cut: 14
        fill: Theme.raised; fillOpacity: 0.78; fill2: Theme.bgBottom; fill2Opacity: 0.72
        stroke: panel.highlighted ? panel.tint : Theme.line
        brackets: !Theme.lacquer; bracketColour: panel.tint
        edgeGlow: true; glowColour: panel.tint
    }
    // Header.
    Item {
        visible: panel.title.length > 0
        x: panel.padding; y: 0; width: parent.width - 2 * panel.padding; height: panel.headerHeight
        Item {
            id: badge
            width: Theme.lacquer ? 18 : 26; height: 26; anchors.verticalCenter: parent.verticalCenter
            Rectangle { visible: !Theme.lacquer; anchors.centerIn: parent; width: 19; height: 19; rotation: 45; color: "transparent"
                        border.width: 1; border.color: Qt.rgba(panel.tint.r, panel.tint.g, panel.tint.b, 0.55) }
            Rectangle { visible: !Theme.lacquer; anchors.centerIn: parent; width: 26; height: 26; radius: 13
                        color: Qt.rgba(panel.tint.r, panel.tint.g, panel.tint.b, 0.07) }
            Glyph { anchors.centerIn: parent; width: Theme.lacquer ? 15 : 13; height: width; kind: panel.glyph || "core"; stroke: panel.tint
                    opacity: Theme.lacquer ? 0.85 : 1 }
        }
        Text {
            x: badge.width + 10; anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x - metaText.implicitWidth - 12; elide: Text.ElideRight
            text: Theme.label(panel.title); color: Theme.holo ? Qt.lighter(Theme.accent, 1.3) : Theme.text
            font.family: Theme.lacquer ? Qt.application.font.family : Theme.monoFont
            font.pixelSize: Theme.lacquer && !Theme.holo ? 14 : 11; font.letterSpacing: Theme.caps ? 2.2 : 0.2; font.bold: !Theme.lacquer
            font.weight: Theme.holo ? Font.DemiBold : Theme.lacquer ? Font.Medium : Font.Bold
        }
        Text {
            id: metaText
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            text: panel.meta; color: panel.metaColour; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: 1.2
        }
        // Divider: bright under the title, fading out to the right.
        Rectangle {
            anchors.bottom: parent.bottom; width: parent.width; height: 1
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.lacquer ? Theme.line : Qt.rgba(panel.tint.r, panel.tint.g, panel.tint.b, 0.55) }
                GradientStop { position: 0.45; color: Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 0.8) }
                GradientStop { position: 1; color: Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 0.15) } }
        }
        Rectangle { anchors.bottom: parent.bottom; anchors.bottomMargin: Theme.lacquer && !Theme.holo ? 0 : -1
                    width: Theme.lacquer && !Theme.holo ? 22 : 34; height: Theme.lacquer && !Theme.holo ? 1.2 : 2; color: panel.tint }
    }
    Column {
        id: column
        x: panel.padding; y: panel.headerHeight + (panel.title.length > 0 ? 14 : panel.padding)
        width: parent.width - 2 * panel.padding
        spacing: panel.spacing
    }
}
