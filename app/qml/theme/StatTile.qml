import QtQuick

// A glowing number tile: value, label, optional sub line and fill bar.
// `tint` colours the value, bar and edge light; `live` makes the edge glow.
Item {
    id: tile
    property string value: "0"
    property string label: ""
    property string sub: ""
    property string glyph: ""
    property color tint: Theme.accent
    property bool live: true
    property real fraction: -1          // 0..1 draws a bar; -1 hides it
    property bool compact: false         // shorter tile for dense pages (Atlas)
    property int order: 0
    property real reveal: 1
    implicitWidth: 180
    implicitHeight: compact ? 60 : 82

    readonly property real local: Math.max(0, Math.min(1, reveal * 1.8 - order * 0.12))
    opacity: local
    transform: Translate { y: (1 - tile.local) * 14 }

    Chamfer { anchors.fill: parent; cut: 10; fill: Theme.raised; fillOpacity: 0.8; fill2: Theme.bgBottom; fill2Opacity: 0.75
              stroke: tile.live ? Qt.rgba(tile.tint.r, tile.tint.g, tile.tint.b, 0.55) : Theme.line
              edgeGlow: tile.live; glowColour: tile.tint }
    Rectangle {
        visible: !Theme.lacquer
        x: 1; y: 10; width: 40; height: parent.height - 20
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.rgba(tile.tint.r, tile.tint.g, tile.tint.b, tile.live ? 0.16 : 0.05) }
            GradientStop { position: 1; color: "transparent" } }
    }
    Rectangle { visible: !Theme.lacquer; x: 0; y: 14; width: 2.5; height: parent.height - 28; color: tile.live ? tile.tint : Theme.line }
    Glyph { visible: tile.glyph.length > 0; anchors.right: parent.right; anchors.rightMargin: 12; y: tile.compact ? 10 : 14
            width: tile.compact ? 14 : 18; height: width
            kind: tile.glyph; stroke: tile.live ? tile.tint : Theme.muted; opacity: 0.85 }
    Column {
        x: 16; y: tile.compact ? 8 : 11; width: parent.width - 40; spacing: tile.compact ? 0 : 1
        Text { text: Theme.label(tile.label); color: Theme.muted; font.family: Theme.lacquer ? Qt.application.font.family : Theme.monoFont
               font.pixelSize: Theme.lacquer ? 11 : 9; font.letterSpacing: Theme.caps ? 1.6 : 0.2; elide: Text.ElideRight; width: parent.width }
        Row {
            spacing: 8
            Text { id: big; text: tile.value
                   style: Theme.holo ? Text.Outline : Text.Normal; styleColor: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.18)
                   // Lacquer: numbers in APVIS's serif, in text colour; only a non-brass tint (attention, info) colours them.
                   color: Theme.lacquer ? (tile.live && !Qt.colorEqual(tile.tint, Theme.accent) ? tile.tint : Theme.text) : (tile.live ? tile.tint : Theme.text)
                   font.family: Theme.lacquer ? (Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family) : Qt.application.font.family
                   font.pixelSize: (tile.compact ? 22 : 28) + (Theme.lacquer ? 4 : 0); font.weight: Theme.lacquer ? Font.Normal : Font.Light
                   font.features: Theme.lacquer ? { "lnum": 1, "pnum": 1 } : ({}) }
            Text { anchors.baseline: big.baseline; text: tile.sub; color: Theme.muted; font.pixelSize: 11; elide: Text.ElideRight
                   width: Math.min(implicitWidth, tile.width - big.width - 60) }
        }
    }
    Item {
        visible: tile.fraction >= 0
        x: 16; width: parent.width - 32; height: 3; anchors.bottom: parent.bottom; anchors.bottomMargin: tile.compact ? 7 : 10
        Rectangle { anchors.fill: parent; color: Theme.line; opacity: 0.6; radius: 1.5; height: Theme.lacquer ? 2 : 3 }
        Rectangle { height: parent.height; radius: 1.5; width: parent.width * Math.max(0, Math.min(1, tile.fraction)); color: tile.tint
                    Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } } }
    }
    Accessible.role: Accessible.StaticText
    Accessible.name: label + ": " + value + (sub ? " " + sub : "")
}
