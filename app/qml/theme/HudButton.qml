import QtQuick
import QtQuick.Controls

// The APVIS button: chamfered panel, a soft accent glow that fades in on hover,
// a slight press, and a clear focus ring for keyboard use. Only opacity and
// scale animate (cheap on every renderer); the chamfer canvases paint once.
Button {
    id: b
    property string caption: ""
    property string glyph: ""
    property string tone: "normal"       // normal | primary | warning | selected
    readonly property color toneColour: tone === "warning" ? Theme.attention : Theme.accent
    implicitHeight: 40
    implicitWidth: Math.max(88, label.implicitWidth + (glyph ? 52 : 32))
    Accessible.name: caption
    scale: pressed ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

    background: Item {
        Chamfer { anchors.fill: parent; cut: 7; fill: b.tone === "primary" ? b.toneColour : Theme.raised
                  fillOpacity: b.tone === "primary" ? 0.95 : 0.85
                  stroke: b.tone === "selected" || b.tone === "warning" ? b.toneColour : Theme.line }
        // Hover / armed glow.
        Chamfer { anchors.fill: parent; cut: 7; fill: b.toneColour; fillOpacity: Theme.lacquer ? 0.06 : 0.16; stroke: b.toneColour
                  opacity: b.hovered || b.tone === "selected" || b.tone === "warning" ? 1 : 0
                  Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } } }
        // Keyboard focus ring.
        Chamfer { anchors.fill: parent; anchors.margins: -3; cut: 9; fill: "transparent"; fillOpacity: 0
                  stroke: Theme.text; strokeWidth: 1.5
                  opacity: b.visualFocus || b.activeFocus && !b.pressed ? 1 : 0
                  Behavior on opacity { NumberAnimation { duration: 120 } } }
    }
    contentItem: Item {
        Row {
            anchors.centerIn: parent; spacing: 8
            Glyph { visible: b.glyph.length > 0; width: 15; height: 15; kind: b.glyph; anchors.verticalCenter: parent.verticalCenter
                    stroke: b.tone === "primary" ? Theme.bgBottom : b.toneColour }
            Text { id: label; text: b.caption; anchors.verticalCenter: parent.verticalCenter
                   color: b.tone === "primary" ? Theme.bgBottom : Theme.text; font.pixelSize: 12; font.weight: b.tone === "primary" ? Font.DemiBold : Font.Normal }
        }
    }
}
