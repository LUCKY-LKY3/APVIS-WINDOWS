import QtQuick
import "../theme"

// SYSTEM STATUS (owner concept): CPU, memory and storage measured every few
// seconds, and an overall line computed from them. Opens the System page.
GlassCard {
    id: card
    title: "SYSTEM STATUS"
    signal go(string key)
    onOpened: go("system")
    readonly property var sys: shell.system || ({})
    readonly property bool known: !!sys.available
    readonly property var issues: {
        if (!known) return ["Measurements unavailable"]
        const out = []
        if (sys.cpu >= 90) out.push("CPU very busy")
        if (sys.memory >= 90) out.push("Memory nearly full")
        if (sys.disk !== null && sys.disk >= 90) out.push("Disk nearly full")
        return out
    }

    component Metric: Item {
        id: m
        property string glyph: ""
        property string label: ""
        property var value: null          // percent or null
        width: parent ? parent.width : 300; height: 44
        readonly property bool high: value !== null && value >= 90
        Glyph { x: 0; anchors.verticalCenter: parent.verticalCenter; width: 19; height: 19; kind: m.glyph; stroke: Theme.accent; opacity: 0.9 }
        Text { x: 36; anchors.verticalCenter: parent.verticalCenter; text: m.label; color: Theme.text; font.pixelSize: 15 }
        Text { anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter
               text: m.value === null ? "—" : Math.round(m.value) + "%"; color: m.high ? Theme.attention : Theme.text; font.pixelSize: 15 }
        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: "›"; color: Theme.muted; font.pixelSize: 17 }
        // Load under the row, like a quiet gauge.
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line; opacity: 0.8 }
        Rectangle { anchors.bottom: parent.bottom; height: 1.5; width: parent.width * Math.max(0, Math.min(1, (m.value || 0) / 100))
                    color: m.high ? Theme.attention : Theme.accent; opacity: 0.75
                    Behavior on width { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } } }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: card.go("system") }
    }
    spacing: 0
    Metric { glyph: "cpu"; label: "CPU"; value: card.known ? card.sys.cpu : null }
    Metric { glyph: "memory"; label: "Memory"; value: card.known ? card.sys.memory : null }
    Metric { glyph: "storage"; label: "Storage"; value: card.known && card.sys.disk !== null ? card.sys.disk : null }
    Item {
        width: parent.width; height: 42
        Rectangle {
            x: 4; anchors.verticalCenter: parent.verticalCenter; width: 9; height: 9; radius: 4.5
            color: card.issues.length ? Theme.attention : Theme.accent
            Rectangle { anchors.centerIn: parent; width: 19; height: 19; radius: 9.5; color: parent.color; opacity: 0.2 }
        }
        Text { x: 26; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 30; elide: Text.ElideRight
               text: card.issues.length ? card.issues.join(" · ") : "All systems operational"
               color: Theme.text; font.pixelSize: 13 }
    }
}
