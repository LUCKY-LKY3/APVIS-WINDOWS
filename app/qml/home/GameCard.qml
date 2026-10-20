import QtQuick
import "../theme"

// NOW PLAYING (APVIS for Windows, game mode): the game that's running and what it costs right now; between games,
// today's playtime and the last game. Opens the Game page.
GlassCard {
    id: card
    property var g: ({})
    readonly property var gpu: g.gpu || null
    readonly property bool playing: !!g.active
    title: playing ? "NOW PLAYING" : "GAME"
    live: playing
    signal go(string key)
    onOpened: go("page:game")
    property real now: Date.now()
    Timer { interval: 1000; repeat: true; running: card.visible && card.playing; onTriggered: card.now = Date.now() }
    function span(seconds) {
        const s = Math.max(0, Math.round(seconds || 0)), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60)
        return h > 0 ? h + " h " + (m < 10 ? "0" : "") + m + " min" : m > 0 ? m + " min" : s + " s"
    }
    readonly property real todaySeconds: (g.today || []).reduce((t, x) => t + (x.seconds || 0), 0)
    spacing: 8

    Text {
        width: parent.width; elide: Text.ElideRight
        text: card.playing ? (card.g.name || "A game") : (card.g.recent || []).length ? "Last played: " + card.g.recent[0].name : "No game running"
        color: Theme.text; font.pixelSize: card.playing ? 20 : 15
        font.family: card.playing && Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family
    }
    Text {
        color: Theme.muted; font.pixelSize: 12
        text: card.playing ? "Playing for " + card.span(card.g.since_ms ? (card.now - card.g.since_ms) / 1000 : card.g.sessionSeconds)
                           : card.todaySeconds > 0 ? "Played today: " + card.span(card.todaySeconds) : "Start a game and APVIS follows it."
    }
    // Three live readings (only while playing): GPU, GPU temperature, CPU.
    Row {
        visible: card.playing
        width: parent.width; spacing: 10
        Repeater {
            model: [
                ["GPU", card.gpu && card.gpu.util !== null ? card.gpu.util + "%" : "—", card.gpu && card.gpu.util !== null ? card.gpu.util / 100 : 0],
                ["TEMP", card.gpu && card.gpu.temp !== null ? card.gpu.temp + "°" : "—", card.gpu && card.gpu.temp ? Math.min(1, card.gpu.temp / 95) : 0],
                ["CPU", card.g.cpu !== undefined ? Math.round(card.g.cpu) + "%" : "—", (card.g.cpu || 0) / 100]
            ]
            delegate: Item {
                required property var modelData
                width: (parent.width - 20) / 3; height: 46
                Text { text: Theme.label(modelData[0]); color: Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.6 }
                Text { y: 13; text: modelData[1]; color: Theme.text; font.pixelSize: 17; font.family: Theme.monoFont }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; radius: 1; color: Theme.line
                    Rectangle { width: parent.width * Math.max(0, Math.min(1, modelData[2])); height: 2; radius: 1
                                color: modelData[2] > 0.9 ? Theme.attention : Theme.accent
                                Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } } } }
            }
        }
    }
}
