import QtQuick
import QtQuick.Controls
import "../theme"

// The Home terminal card: a small APVIS terminal. It greets with fastfetch
// and takes a handful of safe commands (help, cpu, mem, disk, ip, check,
// models, open…, ask…). Nothing typed here runs as a program; `terminal`
// opens a real one. Click to type; Esc goes back to Ask.
Item {
    id: card
    signal action(string key)
    signal released()                       // Esc: give the keyboard back
    readonly property var host: shell.host || ({})
    // Shown as the display name (e.g. "lucky") when the account has one.
    readonly property string prompt: ((host.name || "").split(" ")[0].toLowerCase() || host.user || "apvis") + "@" + (host.hostname || "apvis") + ":~$"
    property var history: []
    property int historyAt: -1
    implicitHeight: 212

    ListModel { id: out }
    function add(lines) {
        for (const l of lines) out.append({ t: l.t || "", c: l.c || "text", r: l.r || "", p: false })
        while (out.count > 200) out.remove(0)
        Qt.callLater(() => view.positionViewAtEnd())
    }
    function run(line) {
        out.append({ t: line, c: "text", r: "", p: true })
        if (line.trim()) { history.push(line); historyAt = history.length }
        shell.miniTerminal(line)
    }
    Connections {
        target: shell
        function onMiniTerminalOutput(result) {
            if (result.action === "clear") out.clear()
            card.add(result.lines || [])
            if (result.action && result.action !== "clear") card.action(result.action)
        }
    }
    Component.onCompleted: { out.append({ t: "fastfetch", c: "text", r: "", p: true }); shell.miniTerminal("fastfetch") }

    Chamfer {
        anchors.fill: parent; cut: 12
        fill: Theme.terminal; fillOpacity: 0.9
        stroke: input.activeFocus ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.6) : Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 0.95)
        edgeGlow: true
    }
    // Title bar.
    Item {
        id: bar
        x: 14; y: 8; width: parent.width - 28; height: 22
        Row {
            anchors.verticalCenter: parent.verticalCenter; spacing: 6
            Repeater { model: 3; delegate: Rectangle { width: 8; height: 8; radius: 4; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.25 + index * 0.25) } }
        }
        Text { anchors.centerIn: parent; text: "APVIS terminal"; color: Theme.muted; font.pixelSize: 11 }
        Text {
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            text: "full terminal ↗"; color: fullMouse.containsMouse ? Theme.accent : Theme.muted; font.pixelSize: 11
            MouseArea { id: fullMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: card.action("launch:terminal") }
        }
    }
    ListView {
        id: view
        x: 14; y: bar.y + bar.height + 4; width: parent.width - 28
        height: inputRow.y - y - 2
        clip: true; model: out; boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: HudScrollBar {}
        delegate: Row {
            required property string t
            required property string c
            required property string r
            required property bool p
            spacing: 10
            Text {
                textFormat: Text.PlainText
                text: p ? card.prompt + " " + t : t
                color: p ? Theme.text : c === "accent" ? Theme.accent : c === "muted" ? Theme.muted : c === "warn" ? Theme.attention : Theme.text
                font.family: Theme.monoFont; font.pixelSize: 12; lineHeight: c === "accent" ? 0.92 : 1.0
                width: r ? implicitWidth : view.width - 12; wrapMode: r ? Text.NoWrap : Text.WrapAnywhere
            }
            Text {
                visible: r.length > 0
                textFormat: Text.StyledText
                text: r.indexOf(":") > 0 ? "<font color='" + Theme.accent + "'>" + r.slice(0, r.indexOf(":") + 1) + "</font>" + r.slice(r.indexOf(":") + 1) : r
                color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 12
                width: view.width - x - 12; elide: Text.ElideRight
            }
        }
    }
    Row {
        id: inputRow
        x: 14; width: parent.width - 28; height: 22
        y: parent.height - height - 10
        spacing: 8
        Text { anchors.verticalCenter: parent.verticalCenter; text: card.prompt; color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 12 }
        TextInput {
            id: input
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x; color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 12
            selectByMouse: true; cursorVisible: activeFocus
            Accessible.name: "APVIS terminal command"
            Text { visible: !input.text && !input.activeFocus; text: "type help"; color: Theme.muted; font: input.font }
            onAccepted: { card.run(text); text = "" }
            Keys.onEscapePressed: card.released()
            Keys.onUpPressed: if (card.historyAt > 0) { card.historyAt--; text = card.history[card.historyAt] }
            Keys.onDownPressed: { if (card.historyAt < card.history.length - 1) { card.historyAt++; text = card.history[card.historyAt] } else { card.historyAt = card.history.length; text = "" } }
        }
    }
    TapHandler { onTapped: input.forceActiveFocus() }
}
