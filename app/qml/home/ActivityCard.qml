import QtQuick
import "../theme"

// RECENT ACTIVITY (owner concept): what really happened, newest first —
// missions, memories saved, updates installed — with how long ago.
GlassCard {
    id: card
    title: "RECENT ACTIVITY"
    signal go(string key)
    onOpened: go("missions")
    property int rows: 4
    property real now: Date.now()
    Timer { interval: 30000; running: card.visible; repeat: true; onTriggered: card.now = Date.now() }
    readonly property var items: {
        const list = (shell.missions || []).map(m => ({
            glyph: m.status === "completed" ? "check" : "mission",
            text: (m.status === "completed" ? "Done: " : m.status === "failed" ? "Didn't complete: " :
                   m.status === "approval_required" ? "Waiting: " : m.status === "cancelled" ? "Cancelled: " : "") + m.preview,
            when: m.updatedAt, warn: m.status === "failed" || m.status === "approval_required" }))
        for (const n of (shell.notes || []).slice(0, 6))
            list.push({ glyph: "memory", text: "Remembered: " + n.title, when: n.updated, warn: false })
        for (const h of ((shell.updates || {}).history || []).slice(0, 4))
            list.push({ glyph: "restart", text: (h.event === "installed" ? "Updated to " : h.event === "rolledback" ? "Rolled back " : h.event + " ") + h.version,
                        when: String(h.at || "").replace(" ", "T"), warn: h.event === "rolledback" })
        list.sort((a, b) => (Date.parse(b.when) || 0) - (Date.parse(a.when) || 0))
        return list.slice(0, card.rows)
    }
    function ago(stamp) {
        const t = Date.parse(stamp)
        if (isNaN(t)) return ""
        const s = Math.max(0, (now - t) / 1000)
        return s < 60 ? "now" : s < 3600 ? Math.round(s / 60) + "m ago" : s < 86400 ? Math.round(s / 3600) + "h ago" : Math.round(s / 86400) + "d ago"
    }
    spacing: 4
    Repeater {
        model: card.items
        delegate: Item {
            required property var modelData
            width: parent.width; height: 32
            Glyph { anchors.verticalCenter: parent.verticalCenter; width: 17; height: 17; kind: modelData.glyph
                    stroke: modelData.warn ? Theme.attention : Theme.accent }
            Text { x: 32; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 32 - whenText.width - 10
                   text: modelData.text; color: Theme.text; font.pixelSize: 13; elide: Text.ElideRight }
            Text { id: whenText; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                   text: card.ago(modelData.when); color: Theme.muted; font.pixelSize: 12 }
        }
    }
    Text {
        visible: card.items.length === 0
        width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 12
        text: "Nothing yet. Missions you run, memories you keep and updates you install appear here."
    }
}
