import QtQuick
import QtQuick.Controls
import "../theme"

// Game (APVIS for Windows, game mode): the game you're playing and what it costs this PC, measured live —
// CPU, GPU, temperature, graphics memory — plus today's and recent playtime. Real readings only: when a number
// isn't measured (e.g. FPS without PresentMon) it says so.
Item {
    id: page
    property var g: ({})
    readonly property var gpu: g.gpu || null
    readonly property bool playing: !!g.active
    property real reveal: 1
    property real now: Date.now()
    Timer { interval: 1000; repeat: true; running: page.visible && page.playing; onTriggered: page.now = Date.now() }
    NumberAnimation { id: entry; target: page; property: "reveal"; from: 0; to: 1; duration: 700; easing.type: Easing.OutCubic }
    onVisibleChanged: if (visible) entry.restart()

    function span(seconds) {
        const s = Math.max(0, Math.round(seconds || 0)), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60)
        return h > 0 ? h + " h " + (m < 10 ? "0" : "") + m + " min" : m > 0 ? m + " min" : s + " s"
    }
    function ago(ms) {
        if (!ms) return ""
        const s = Math.max(0, (Date.now() - ms) / 1000)
        return s < 120 ? "just now" : s < 3600 ? Math.round(s / 60) + " min ago" : s < 86400 ? Math.round(s / 3600) + " h ago" : Math.round(s / 86400) + " days ago"
    }
    readonly property real sessionSeconds: playing && g.since_ms ? (now - g.since_ms) / 1000 : (g.sessionSeconds || 0)
    readonly property real todaySeconds: (g.today || []).reduce((t, x) => t + (x.seconds || 0), 0)
    function num(v, unit) { return v === null || v === undefined ? "—" : Math.round(v) + unit }

    PageHeader {
        id: header
        width: parent.width
        code: "G"; title: "GAME"; reveal: page.reveal
        subtitle: "What you're playing and what it asks of this PC, measured live."
    }

    // ---- now playing: the hero
    Item {
        id: hero
        anchors.top: header.bottom; anchors.topMargin: 18
        width: parent.width; height: 132
        opacity: Math.min(1, page.reveal * 1.6)
        Chamfer { anchors.fill: parent; cut: 16; fill: Theme.raised; fillOpacity: 0.78; fill2: Theme.bgBottom; fill2Opacity: 0.72
                  edgeGlow: page.playing; glowColour: Theme.accent; brackets: true }
        Column {
            x: 28; anchors.verticalCenter: parent.verticalCenter; spacing: 6
            width: parent.width * 0.62
            Row {
                spacing: 10
                Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4
                            color: page.playing ? Theme.accent : Theme.muted
                            SequentialAnimation on opacity { running: page.playing && page.visible; loops: Animation.Infinite
                                NumberAnimation { to: 0.35; duration: 1200; easing.type: Easing.InOutSine }
                                NumberAnimation { to: 1; duration: 1200; easing.type: Easing.InOutSine } } }
                Text { text: Theme.label(page.playing ? "NOW PLAYING" : "NO GAME RUNNING"); color: page.playing ? Theme.accent : Theme.muted
                       font.pixelSize: 11; font.letterSpacing: 2.2 }
            }
            Text {
                width: parent.width; elide: Text.ElideRight
                text: page.playing ? (page.g.name || "A game") : "Start a game and APVIS follows it here"
                color: Theme.text; font.pixelSize: page.playing ? 38 : 26; font.weight: Font.Light
                font.family: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family
            }
            Text {
                color: Theme.muted; font.pixelSize: 13
                text: page.playing ? "Playing for " + page.span(page.sessionSeconds) + (page.g.exe ? "   ·   " + page.g.exe : "")
                                   : !page.g.available ? "Game mode runs in APVIS for Windows."
                                   : page.todaySeconds > 0 ? "Played today: " + page.span(page.todaySeconds) : "Nothing played yet today."
            }
        }
        Column {
            anchors.right: parent.right; anchors.rightMargin: 28; anchors.verticalCenter: parent.verticalCenter; spacing: 4
            Text { anchors.right: parent.right; text: Theme.label("TODAY"); color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 2 }
            Text { anchors.right: parent.right; text: page.todaySeconds > 0 ? page.span(page.todaySeconds) : "—"; color: Theme.text
                   font.pixelSize: 24; font.family: Theme.monoFont }
            Text { anchors.right: parent.right; color: Theme.muted; font.pixelSize: 11
                   text: (page.g.today || []).length === 1 ? "one game" : (page.g.today || []).length + " games" }
        }
    }

    // ---- live readings
    Row {
        id: tiles
        anchors.top: hero.bottom; anchors.topMargin: 14
        width: parent.width; spacing: 12
        readonly property real w: (width - 3 * spacing) / 4
        StatTile { width: tiles.w; order: 0; reveal: page.reveal; label: "CPU"; glyph: "cpu"
                   value: page.num(page.g.cpu, "%"); fraction: page.g.cpu !== undefined ? (page.g.cpu || 0) / 100 : -1
                   sub: page.playing && page.g.procCpu !== null && page.g.procCpu !== undefined ? "game " + Math.round(page.g.procCpu) + "%" : "whole PC"
                   tint: page.g.cpu >= 90 ? Theme.attention : Theme.accent }
        StatTile { width: tiles.w; order: 1; reveal: page.reveal; label: "GPU"; glyph: "chip"
                   value: page.gpu ? page.num(page.gpu.util, "%") : "—"; fraction: page.gpu && page.gpu.util !== null ? page.gpu.util / 100 : -1
                   sub: page.gpu ? (page.gpu.clock ? page.gpu.clock + " MHz" : page.gpu.name || "") : "no NVIDIA readings"
                   tint: page.gpu && page.gpu.util >= 95 ? Theme.attention : Theme.accent }
        StatTile { width: tiles.w; order: 2; reveal: page.reveal; label: "GPU TEMP"; glyph: "activity"
                   value: page.gpu ? page.num(page.gpu.temp, "°C") : "—"; fraction: page.gpu && page.gpu.temp ? Math.min(1, page.gpu.temp / 95) : -1
                   sub: page.gpu && page.gpu.fan !== null && page.gpu.fan !== undefined ? "fan " + page.gpu.fan + "%" : ""
                   tint: page.gpu && page.gpu.temp >= 83 ? Theme.attention : Theme.accent }
        StatTile { width: tiles.w; order: 3; reveal: page.reveal; label: "GRAPHICS MEMORY"; glyph: "memory"
                   value: page.gpu && page.gpu.vramUsed !== null ? (page.gpu.vramUsed / 1024).toFixed(1) + " GB" : "—"
                   fraction: page.gpu && page.gpu.vramTotal ? page.gpu.vramUsed / page.gpu.vramTotal : -1
                   sub: page.gpu && page.gpu.vramTotal ? "of " + (page.gpu.vramTotal / 1024).toFixed(0) + " GB" : "" }
    }

    Flickable {
        anchors.top: tiles.bottom; anchors.topMargin: 14; anchors.bottom: parent.bottom
        width: parent.width; contentHeight: grid.height + 10; clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: HudScrollBar {}
        Flow {
            id: grid
            width: parent.width - 12; spacing: 14
            readonly property real half: (width - spacing) / 2

            HudPanel {
                width: grid.half; reveal: page.reveal; order: 4
                title: "LOAD"; glyph: "activity"; meta: "LAST FIVE MINUTES"
                Text { text: "GPU  ·  CPU"; color: Theme.muted; font.pixelSize: 11 }
                Sparkline { width: parent.width; height: 96; values: (page.g.history || {}).gpu || []; second: (page.g.history || {}).cpu || []; maxValue: 100 }
                Text { text: "GPU temperature (°C)"; color: Theme.muted; font.pixelSize: 11 }
                Sparkline { width: parent.width; height: 64; values: (page.g.history || {}).gpuTemp || []; maxValue: 100 }
            }
            HudPanel {
                width: grid.half; reveal: page.reveal; order: 5
                title: "THIS PC"; glyph: "device"; meta: page.gpu ? Theme.label(page.gpu.name || "") : ""
                Repeater {
                    model: [
                        ["Graphics card", page.gpu ? page.gpu.name || "—" : "No NVIDIA card found"],
                        ["GPU power", page.gpu && page.gpu.power !== null && page.gpu.power !== undefined ? Math.round(page.gpu.power) + " W" : "—"],
                        ["GPU clock", page.gpu && page.gpu.clock ? page.gpu.clock + " MHz" : "—"],
                        ["Memory in use", page.num(page.g.ram, "%")],
                        ["Game process", page.playing && page.g.procRamMb ? page.g.procRamMb + " MB RAM" : "—"],
                        ["Frame rate", page.g.fps !== null && page.g.fps !== undefined ? Math.round(page.g.fps) + " fps" : "not measured"]
                    ]
                    delegate: Item {
                        required property var modelData
                        width: parent.width; height: 30
                        Text { anchors.verticalCenter: parent.verticalCenter; text: modelData[0]; color: Theme.muted; font.pixelSize: 13 }
                        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: modelData[1]
                               color: Theme.text; font.pixelSize: 13; width: parent.width * 0.6; horizontalAlignment: Text.AlignRight; elide: Text.ElideLeft }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line; opacity: 0.6 }
                    }
                }
            }
            HudPanel {
                width: grid.width; reveal: page.reveal; order: 6
                title: "RECENT GAMES"; glyph: "clock"; meta: (page.g.recent || []).length ? (page.g.recent || []).length + " TRACKED" : ""
                Text { visible: !(page.g.recent || []).length; text: "Games you play show up here with how long you've played them."
                       color: Theme.muted; font.pixelSize: 13 }
                Repeater {
                    model: page.g.recent || []
                    delegate: Item {
                        required property var modelData
                        width: parent.width; height: 38
                        Text { x: 4; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.5; elide: Text.ElideRight
                               text: modelData.name; color: Theme.text; font.pixelSize: 14 }
                        Text { x: parent.width * 0.52; anchors.verticalCenter: parent.verticalCenter; text: page.span(modelData.totalSeconds)
                               color: Theme.accent; font.pixelSize: 13; font.family: Theme.monoFont }
                        Text { anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                               text: page.ago(modelData.lastPlayedMs); color: Theme.muted; font.pixelSize: 12 }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line; opacity: 0.5 }
                    }
                }
            }
        }
    }
}
