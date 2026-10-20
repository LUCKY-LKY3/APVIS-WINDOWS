import QtQuick
import "../theme"

// The brand block (owner concept): the faceted mark, name and version, and
// what APVIS is for.
Item {
    id: brand
    property string version: ""
    property real markSize: 104
    implicitWidth: row.width
    implicitHeight: row.height
    Row {
        id: row
        spacing: 22
        // The logo is the name itself (owner, 2026-10-09): "APVIS", wide-spaced in the serif.
        Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            Row {
                spacing: 8
                Text { id: name; text: "APVIS"; color: Theme.text; font.pixelSize: brand.markSize * 0.34; font.weight: Font.Normal; font.letterSpacing: brand.markSize * 0.12
                       font.family: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family }
                Text { anchors.baseline: name.baseline; text: brand.version; color: Theme.muted; font.pixelSize: 11 }
            }

        }
    }
}
