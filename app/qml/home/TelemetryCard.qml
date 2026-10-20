import QtQuick
import "../theme"

// TELEMETRY (APVIS for Windows): the last few minutes of CPU and memory as a graph,
// then the graphics card and network as a dense readout. Measured values only;
// anything not measured shows a dash. Opens the System page.
GlassCard {
    id: card
    title: "TELEMETRY"
    signal go(string key)
    onOpened: go("system")
    readonly property var sys: shell.telemetry || ({})      // the sampler's readings (history, RAM, rates)
    readonly property var hist: sys.history || ({})
    readonly property var gpu: (shell.game || {}).gpu || null
    function last(list) { return list && list.length ? list[list.length - 1] : null }
    function rate(v) { return v === null || v === undefined ? "—" : v >= 1048576 ? (v / 1048576).toFixed(1) + " MB/s" : Math.round(v / 1024) + " KB/s" }
    function val(v, unit) { return v === null || v === undefined ? "—" : Math.round(v) + unit }
    spacing: 6

    Item {
        width: parent.width; height: 14
        Row {
            spacing: 14
            Row { spacing: 5; Rectangle { y: 4; width: 10; height: 2; color: Theme.accent }
                  Text { text: Theme.label("CPU"); color: Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.4 } }
            Row { spacing: 5; Rectangle { y: 4; width: 10; height: 2; color: Theme.warm }
                  Text { text: Theme.label("MEMORY"); color: Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.4 } }
        }
        Text { anchors.right: parent.right; text: Theme.label("LAST 5 MIN"); color: Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.4 }
    }
    Sparkline { width: parent.width; height: 62; values: card.hist.cpu || []; second: card.hist.memory || []; maxValue: 100 }
    Grid {
        width: parent.width; columns: 2; columnSpacing: 18; rowSpacing: 0
        Repeater {
            model: [
                ["GPU TEMP", card.gpu ? card.val(card.gpu.temp, "°C") : "—"],
                ["GPU POWER", card.gpu ? card.val(card.gpu.power, " W") : "—"],
                ["GPU CLOCK", card.gpu && card.gpu.clock ? card.gpu.clock + " MHz" : "—"],
                ["GPU FAN", card.gpu ? card.val(card.gpu.fan, "%") : "—"],
                ["NET DOWN", card.rate(card.last(card.hist.down))],
                ["NET UP", card.rate(card.last(card.hist.up))],
                ["RAM", card.sys.memoryUsedGb ? card.sys.memoryUsedGb + " / " + Math.round(card.sys.memoryTotalGb) + " GB" : "—"],
                ["VRAM", card.gpu && card.gpu.vramTotal ? (card.gpu.vramUsed / 1024).toFixed(1) + " / " + Math.round(card.gpu.vramTotal / 1024) + " GB" : "—"]
            ]
            delegate: Item {
                required property var modelData
                width: (card.width - 2 * card.padding - 18) / 2; height: 27
                Text { anchors.verticalCenter: parent.verticalCenter; text: Theme.label(modelData[0]); color: Theme.muted
                       font.pixelSize: 10; font.letterSpacing: 1.2 }
                Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: modelData[1]
                       color: Theme.text; font.pixelSize: 12; font.family: Theme.monoFont }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line; opacity: 0.55 }
            }
        }
    }
}
