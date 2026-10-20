import QtQuick
import QtQuick.Controls
import "../theme"

// System: a live monitor of this computer (measured every ~3 s by the status
// thread): load history, per-core use, temperatures, and the busiest
// programs. Your own programs can be ended (press twice); Home itself cannot.
Item {
    id: page
    readonly property var sys: shell.system || ({})
    readonly property var tel: shell.telemetry || ({})
    readonly property var hist: tel.history || ({})
    readonly property string me: (shell.host || {}).user || ""
    property int armed: -1
    Timer { id: disarm; interval: 4000; onTriggered: page.armed = -1 }
    onVisibleChanged: { shell.setSystemPageVisible(visible); if (visible) entry.restart() }
    property real reveal: 1
    NumberAnimation { id: entry; target: page; property: "reveal"; from: 0; to: 1; duration: 800; easing.type: Easing.OutCubic }
    function rate(n) { return n === undefined || n === null ? "—" : n < 1024 ? n + " B/s" : n < 1048576 ? (n / 1024).toFixed(1) + " KB/s" : (n / 1048576).toFixed(1) + " MB/s" }
    function last(a) { return a && a.length ? a[a.length - 1] : null }

    PageHeader {
        id: header
        width: parent.width
        code: "07"; title: "SYSTEM"; reveal: page.reveal
        subtitle: "This computer right now: measured every few seconds, nothing estimated."
    }
    Row {
        id: tiles
        anchors.top: header.bottom; anchors.topMargin: 16
        width: parent.width; spacing: 12
        readonly property real w: (width - 3 * spacing) / 4
        StatTile { width: tiles.w; order: 0; reveal: page.reveal; label: "CPU"; glyph: "cpu"
                   value: page.sys.available ? page.sys.cpu + "%" : "—"; sub: page.tel.freqMhz ? (page.tel.freqMhz / 1000).toFixed(2) + " GHz" : ""
                   fraction: page.sys.available ? page.sys.cpu / 100 : -1; tint: page.sys.cpu >= 90 ? Theme.attention : Theme.accent }
        StatTile { width: tiles.w; order: 1; reveal: page.reveal; label: "MEMORY"; glyph: "memory"
                   value: page.sys.available ? page.sys.memory + "%" : "—"
                   sub: page.tel.memoryUsedGb ? page.tel.memoryUsedGb + " / " + page.tel.memoryTotalGb + " GB" : ""
                   fraction: page.sys.available ? page.sys.memory / 100 : -1; tint: page.sys.memory >= 90 ? Theme.attention : Theme.accent }
        StatTile { width: tiles.w; order: 2; reveal: page.reveal; label: "STORAGE"; glyph: "storage"
                   value: page.sys.disk !== null && page.sys.disk !== undefined ? page.sys.disk + "%" : "—"; sub: "home folder's disk"
                   fraction: page.sys.disk ? page.sys.disk / 100 : -1; tint: page.sys.disk >= 90 ? Theme.attention : Theme.accent }
        StatTile { width: tiles.w; order: 3; reveal: page.reveal; label: "NETWORK"; glyph: "wifi"
                   value: "▼ " + page.rate(page.last(page.hist.down)); sub: "▲ " + page.rate(page.last(page.hist.up)) }
    }

    Flickable {
        anchors.top: tiles.bottom; anchors.topMargin: 16; anchors.bottom: parent.bottom
        width: parent.width; contentHeight: grid.height + 10; clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: HudScrollBar {}
        Flow {
            id: grid
            width: parent.width - 12; spacing: 14
            readonly property real half: (width - spacing) / 2

            HudPanel {
                width: grid.half; reveal: page.reveal; order: 4
                title: "LOAD HISTORY"; glyph: "activity"; meta: "LAST FEW MINUTES"
                Text { text: "CPU  ·  memory"; color: Theme.muted; font.pixelSize: 11 }
                Sparkline { width: parent.width; height: 90; values: page.hist.cpu || []; second: page.hist.memory || []; maxValue: 100 }
                Text { text: "Network  ·  ▼ download  ▲ upload"; color: Theme.muted; font.pixelSize: 11 }
                Sparkline { width: parent.width; height: 70; values: page.hist.down || []; second: page.hist.up || [] }
            }
            HudPanel {
                width: grid.half; reveal: page.reveal; order: 5
                title: "CPU CORES"; glyph: "chip"; meta: (page.tel.cores || []).length + " CORES"
                // One column per core across the whole panel (3.0.11: they used to bunch up on the left).
                Row {
                    id: coreRow
                    width: parent.width
                    readonly property int n: Math.max(1, (page.tel.cores || []).length)
                    readonly property real cell: width / n
                    Repeater {
                        model: (page.tel.cores || []).length
                        delegate: Item {
                            required property int index
                            readonly property real modelData: (page.tel.cores || [])[index] || 0
                            readonly property color tone: modelData >= 90 ? Theme.attention : Theme.accent
                            width: coreRow.cell; height: 112
                            Rectangle {
                                id: track
                                anchors.horizontalCenter: parent.horizontalCenter; y: 2
                                width: Math.max(18, Math.min(46, coreRow.cell * 0.32)); height: 78; radius: 4
                                color: Theme.sheen(0.05); border.color: Theme.line
                                // Quarter marks on the track.
                                Repeater { model: 3
                                    Rectangle { required property int index; x: 3; width: track.width - 6; height: 1
                                                y: track.height * (index + 1) / 4; color: Theme.line; opacity: 0.6 } }
                                Rectangle {
                                    anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                                    width: parent.width - 4; anchors.bottomMargin: 2; radius: 3
                                    height: Math.max(2, (parent.height - 4) * Math.min(1, modelData / 100))
                                    gradient: Gradient {
                                        GradientStop { position: 0; color: Qt.lighter(tone, 1.25) }
                                        GradientStop { position: 1; color: Qt.rgba(tone.r, tone.g, tone.b, 0.55) }
                                    }
                                    Behavior on height { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                                }
                            }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; y: 86; text: modelData + "%"; color: Theme.text
                                   font.pixelSize: 13; font.family: Theme.monoFont }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; y: 102; text: Theme.label("CORE " + (index + 1)); color: Theme.muted
                                   font.pixelSize: 9; font.letterSpacing: 1.2 }
                        }
                    }
                }
                Text { visible: !(page.tel.cores || []).length; text: "Measuring…"; color: Theme.muted; font.pixelSize: 12 }
                Rectangle { width: parent.width; height: 1; color: Theme.line }
                Text { text: Theme.label("TEMPERATURES"); color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1.6 }
                Flow {
                    width: parent.width; spacing: 14
                    Repeater {
                        model: page.tel.temps || []
                        delegate: Text { required property var modelData
                                         text: modelData.label + "  " + modelData.c + " °C"; font.pixelSize: 12
                                         color: modelData.c >= 85 ? Theme.attention : Theme.text }
                    }
                }
                Text { visible: !(page.tel.temps || []).length; text: "No temperature sensors reported."; color: Theme.muted; font.pixelSize: 12 }
            }
            HudPanel {
                width: grid.width; reveal: page.reveal; order: 6
                title: "BUSIEST PROGRAMS"; glyph: "cpu"; meta: (page.tel.processCount || 0) + " RUNNING"
                Item {
                    width: parent.width; height: 22
                    Text { x: 0; text: Theme.label("PROGRAM"); color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1.4 }
                    Text { x: parent.width * 0.42; text: Theme.label("CPU"); color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1.4 }
                    Text { x: parent.width * 0.56; text: Theme.label("MEMORY"); color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1.4 }
                    Text { x: parent.width * 0.70; text: Theme.label("OWNER"); color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1.4 }
                }
                Repeater {
                    // A count, not the array: rows stay alive between telemetry ticks and only their
                    // values change (rebuilding every row each tick made scrolling stutter, 3.0.8).
                    model: (page.tel.processes || []).length
                    delegate: Item {
                        id: proc
                        required property int index
                        readonly property var modelData: (page.tel.processes || [])[index] || ({})
                        readonly property bool mine: !!page.me && modelData.user === page.me
                        width: parent.width; height: 34
                        Rectangle { anchors.fill: parent; radius: 6; color: procMouse.containsMouse ? Theme.sheen(0.04) : "transparent" }
                        MouseArea { id: procMouse; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                        Text { x: 4; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.4; elide: Text.ElideRight
                               text: proc.modelData.name; color: Theme.text; font.pixelSize: 13 }
                        Item {
                            x: parent.width * 0.42; width: parent.width * 0.12; height: parent.height
                            Text { anchors.verticalCenter: parent.verticalCenter; text: proc.modelData.cpu + "%"; color: proc.modelData.cpu >= 50 ? Theme.attention : Theme.text; font.pixelSize: 13 }
                        }
                        Text { x: parent.width * 0.56; anchors.verticalCenter: parent.verticalCenter; text: proc.modelData.mem + "%"; color: Theme.text; font.pixelSize: 13 }
                        Text { x: parent.width * 0.70; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.16; elide: Text.ElideRight
                               text: proc.modelData.user || "system"; color: Theme.muted; font.pixelSize: 12 }
                        // Built only for your own programs: rows are rebuilt on every telemetry tick (3.0.7).
                        Loader {
                            active: proc.mine
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            sourceComponent: Component {
                                HudButton {
                                    width: 110; implicitHeight: 28
                                    tone: page.armed === proc.modelData.pid ? "warning" : "normal"
                                    caption: page.armed === proc.modelData.pid ? "Press again" : "End"
                                    Accessible.name: "End " + proc.modelData.name
                                    onClicked: {
                                        if (page.armed === proc.modelData.pid) { page.armed = -1; shell.endProcess(proc.modelData.pid) }
                                        else { page.armed = proc.modelData.pid; disarm.restart() }
                                    }
                                }
                            }
                        }
                    }
                }
                Text { visible: !(page.tel.processes || []).length; text: "Measuring…"; color: Theme.muted; font.pixelSize: 12 }
                Text { width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 11
                       text: "Only your own programs can be ended here, and ending asks the program to close (like closing its window)." }
            }
        }
    }
}
