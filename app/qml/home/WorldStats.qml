import QtQuick
import "../theme"

// The big-number box under the core (APVIS for Windows, after the owner's JARVIS
// dashboard reference): today's world at a glance from the live feed's summary.
// Click opens Intelligence.
Item {
    id: box
    signal go(string key)
    height: 96
    readonly property var sum: (typeof shell.intelSummary !== "undefined" && shell.intelSummary) ? shell.intelSummary : ({})
    readonly property var counts: sum.counts || ({})
    readonly property var sev: sum.severity || ({})
    readonly property bool ready: !!sum.total
    function n(v) { return box.ready ? String(v || 0) : "—" }
    readonly property var stats: [
        ["REPORTS", n(sum.total), "in the live feed", Theme.text],
        ["NOTABLE", n((sev.high || 0) + (sev.medium || 0)), (sev.high || 0) + " high", (sev.high || 0) > 0 ? Theme.attention : Theme.text],
        ["QUAKES", n(counts.quake), "reported by USGS", Theme.text],
        ["STORMS", n((counts.storm || 0) + (counts.cyclone || 0)), "storms and cyclones", Theme.text],
        ["HEADLINES", n((counts.news || 0) + (counts.tech || 0) + (counts.science || 0)), "world, tech, science", Theme.text]
    ]

    Chamfer { anchors.fill: parent; cut: 14; fill: Theme.panel; fillOpacity: 0.72; fill2: Theme.bgBottom; fill2Opacity: 0.8
              stroke: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.45); edgeGlow: true; brackets: true }
    Row {
        anchors.centerIn: parent
        Repeater {
            model: box.stats
            delegate: Item {
                required property var modelData
                required property int index
                width: (box.width - 24) / box.stats.length; height: box.height - 20
                Rectangle { visible: index > 0; width: 1; height: parent.height - 16; anchors.verticalCenter: parent.verticalCenter
                            color: Theme.line }
                Column {
                    anchors.centerIn: parent; spacing: 2
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: Theme.label(modelData[0]); color: Theme.accent
                           font.pixelSize: 10; font.letterSpacing: 2 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData[1]; color: modelData[3]
                           font.pixelSize: 30; font.weight: Font.Light; font.family: Theme.monoFont }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData[2]; color: Theme.muted; font.pixelSize: 10 }
                }
            }
        }
    }
    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: box.go("page:atlas") }
}
