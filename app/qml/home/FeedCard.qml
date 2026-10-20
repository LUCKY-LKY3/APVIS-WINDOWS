import QtQuick
import "../theme"

// LIVE FEED (APVIS for Windows): the newest open-source reports, merged from every
// world layer (quakes, disasters, storms, space weather, headlines), newest first.
// Only real items; the card says so while the first poll is still on its way.
GlassCard {
    id: card
    title: "LIVE ACTIVITY"
    property int rows: 5
    signal go(string key)
    onOpened: go("page:atlas")
    readonly property var feed: (typeof shell.intelFeed !== "undefined" && shell.intelFeed) ? shell.intelFeed : []
    // A QVariantList from Python is list-like, not a JS array. Small quakes (dozens a day) would bury everything
    // else, so only notable ones stay.
    function pick(f) {
        const all = !f ? [] : f.length !== undefined ? Array.prototype.slice.call(f) : Array.prototype.slice.call(f.items || [])
        return all.filter(x => x.kind !== "quake" || x.severity !== "low")
    }
    readonly property var items: pick(feed).slice(0, rows)
    badge: items.length ? "LIVE" : ""
    live: items.length > 0 && items[0].severity === "high"
    tint: Theme.attention
    property real now: Date.now()
    Timer { interval: 30000; repeat: true; running: card.visible; onTriggered: card.now = Date.now() }
    function ago(ms) {
        if (!ms) return ""
        const s = Math.max(0, (card.now - ms) / 1000)
        return s < 90 ? "now" : s < 3600 ? Math.round(s / 60) + "m" : s < 86400 ? Math.round(s / 3600) + "h" : Math.round(s / 86400) + "d"
    }
    spacing: 0

    Text {
        visible: card.items.length === 0
        width: parent.width; wrapMode: Text.WordWrap; bottomPadding: 8
        text: "Waiting for the first reports from the open feeds…"; color: Theme.muted; font.pixelSize: 13
    }
    Repeater {
        model: card.items
        delegate: Item {
            id: row
            required property var modelData
            required property int index
            width: card.width - 2 * card.padding; height: 54
            readonly property color sev: modelData.severity === "high" ? Theme.attention
                                       : modelData.severity === "medium" ? Theme.warm : Theme.accent
            // the timeline: a line through every row and a dot per report
            Rectangle { x: 4; y: row.index === 0 ? 12 : 0; width: 1; height: row.index === card.items.length - 1 ? 12 : parent.height
                        color: Theme.line }
            Rectangle { x: 0; y: 8; width: 9; height: 9; radius: 4.5; color: Theme.bgBottom; border.width: 1.5; border.color: row.sev }
            Text { x: 20; y: 4; text: row.modelData.time_ms ? Qt.formatDateTime(new Date(row.modelData.time_ms), "HH:mm") : ""
                   color: row.sev; font.pixelSize: 10; font.family: Theme.monoFont }
            Text { x: 20; y: 18; width: parent.width - 20 - tag.width - 10; elide: Text.ElideRight
                   text: row.modelData.title || ""; color: Theme.text; font.pixelSize: 13 }
            Text { x: 20; y: 35; width: parent.width - 20 - 40; elide: Text.ElideRight; color: Theme.muted; font.pixelSize: 11
                   text: [row.modelData.place || "", row.modelData.source || ""].filter(x => x).join("  ·  ") }
            Rectangle {
                id: tag
                anchors.right: parent.right; y: 16; height: 18; radius: 3
                width: tagText.implicitWidth + 12
                color: Qt.rgba(row.sev.r, row.sev.g, row.sev.b, 0.12); border.width: 1; border.color: Qt.rgba(row.sev.r, row.sev.g, row.sev.b, 0.6)
                Text { id: tagText; anchors.centerIn: parent; text: (row.modelData.kind || "").toUpperCase(); color: row.sev
                       font.pixelSize: 9; font.letterSpacing: 1.2 }
            }
            Text { anchors.right: parent.right; y: 37; text: card.ago(row.modelData.time_ms); color: Theme.muted
                   font.pixelSize: 10; font.family: Theme.monoFont }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: card.go("page:atlas") }
        }
    }
}
