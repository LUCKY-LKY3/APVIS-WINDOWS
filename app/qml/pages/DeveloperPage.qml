import QtQuick
import QtQuick.Controls
import "../theme"

// Developer Mode (V2-19): actual renderer, services, AI route, feeds, memory,
// missions and logs, each labelled with its source. Refreshes every 3 s while
// open; nothing here is smoothed or illustrative.
Item {
    id: page
    readonly property var d: shell.devInfo || ({})
    readonly property var r: d.renderer || ({})
    onVisibleChanged: if (visible) shell.refreshDev()
    Component.onCompleted: if (visible) shell.refreshDev()
    Timer { interval: 3000; repeat: true; running: page.visible; onTriggered: shell.refreshDev() }

    component Card: Item {
        id: card
        property string title: ""
        property string source: ""
        default property alias content: body.data
        width: (grid.width - 14) / 2; height: body.height + 62
        Chamfer { anchors.fill: parent; cut: 12; fill: Theme.raised; fillOpacity: 0.78; fill2: Theme.bgBottom; fill2Opacity: 0.72
                  stroke: Theme.line; brackets: true; edgeGlow: true }
        Text { x: 14; y: 12; text: card.title; color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 11; font.letterSpacing: Theme.caps ? 2 : 0.3; font.bold: true }
        Text { anchors.right: parent.right; anchors.rightMargin: 14; y: 13; text: card.source; color: Theme.muted; font.pixelSize: 9 }
        Column { id: body; x: 14; y: 38; width: parent.width - 28; spacing: 5 }
    }
    component Line: Row {
        property string k: ""
        property string v: ""
        property color vc: Theme.text
        spacing: 8
        Text { width: 150; text: parent.k; color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10 }
        Text { text: parent.v; color: parent.vc; font.family: Theme.monoFont; font.pixelSize: 11 }
    }
    function stateColour(s) { return s === "active" || s === "running" ? Theme.accent : s === "inactive" || s === "not running" ? Theme.muted : Theme.attention }

    PageHeader {
        id: header
        width: parent.width
        code: "06"; title: "DEVELOPER"
        subtitle: "The real internals, each with its source. Updated " + (page.d.at || "…") + ". Turn Developer mode off in Settings."
    }

    Flickable {
        anchors.fill: parent; anchors.topMargin: header.height + 14
        contentHeight: grid.height + 20; clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: HudScrollBar {}
        Flow {
            id: grid
            width: parent.width - 14; spacing: 14

            Card {
                title: "RENDERER"; source: page.r.source || ""
                Line { k: "renderer"; v: (page.r.renderer || "?") + (page.r.software ? " (software scene graph)" : " (OpenGL)") }
                Line { k: "quality tier"; v: page.r.tier || "?" }
                Line { k: "lite look"; v: page.r.lite ? "yes" : "no" }
                Line { k: "last window"; v: page.r.frame_fps !== undefined ? page.r.frame_fps + " fps · p95 " + page.r.frame_p95 + " ms" : "not measured yet (open Home)" }
                // Frame-rate history from the frame log (one bar per 2 s window).
                Item {
                    width: parent.width; height: 70
                    readonly property var h: page.r.history || []
                    Rectangle { anchors.fill: parent; color: Theme.bgBottom; opacity: 0.6; radius: 3 }
                    Rectangle { x: 0; width: parent.width; height: 1; color: Theme.attention; opacity: 0.5
                                y: parent.height - parent.height * 60 / 70 }
                    Text { x: 4; y: parent.height - parent.height * 60 / 70 - 12; text: "60"; color: Theme.attention; font.pixelSize: 8; opacity: 0.8 }
                    Row {
                        anchors.bottom: parent.bottom; spacing: 1
                        Repeater {
                            model: parent.parent.h
                            delegate: Rectangle {
                                required property var modelData
                                width: Math.max(2, (page.width / 2 - 60) / 62); height: Math.min(70, modelData.fps / 70 * 70)
                                anchors.bottom: parent.bottom
                                color: modelData.tier === "full" ? Theme.accent : modelData.tier === "balanced" ? Theme.signal : Theme.muted
                            }
                        }
                    }
                }
                Text { text: "bars: fps per 2 s window · emerald full · cyan balanced · grey minimal"; color: Theme.muted; font.pixelSize: 9 }
            }

            Card {
                title: "SERVICES"; source: "systemctl / process table"
                Repeater {
                    model: page.d.services || []
                    delegate: Row {
                        required property var modelData
                        spacing: 8
                        Rectangle { width: 7; height: 7; radius: 3.5; anchors.verticalCenter: parent.verticalCenter; color: page.stateColour(modelData.state) }
                        Text { width: 170; text: modelData.name; color: Theme.text; font.pixelSize: 11 }
                        Text { text: modelData.state; color: page.stateColour(modelData.state); font.family: Theme.monoFont; font.pixelSize: 10 }
                    }
                }
            }

            Card {
                title: "AI ROUTE"; source: (page.d.route || {}).source || ""
                Line { k: "endpoint"; v: (page.d.route || {}).endpoint || "?" }
                Line { k: "reachable"; v: (page.d.route || {}).reachable ? "yes" : "no"; vc: (page.d.route || {}).reachable ? Theme.accent : Theme.attention }
                Line { k: "model (fast)"; v: (page.d.route || {}).model || "—" }
                Line { k: "ollama"; v: (page.d.route || {}).version || "—" }
                Line { k: "policy"; v: (page.d.route || {}).policy || "—" }
                Text { visible: !!(page.d.route || {}).error; width: parent.width; wrapMode: Text.WordWrap
                       text: (page.d.route || {}).error || ""; color: Theme.attention; font.pixelSize: 10 }
            }

            Card {
                title: "FEEDS · MEMORY · MISSIONS"; source: "OSIRIS, vault, task store"
                Repeater {
                    model: page.d.feeds || []
                    delegate: Line {
                        required property var modelData
                        k: modelData.name
                        v: modelData.status + (modelData.count !== null && modelData.count !== undefined ? " · " + modelData.count + " aircraft" : "") +
                           (modelData.age_s !== null && modelData.age_s !== undefined ? " · " + modelData.age_s + " s old" : "")
                        vc: modelData.status === "live" ? Theme.accent : Theme.muted
                    }
                }
                Line { k: "memory"; v: ((page.d.memory || {}).notes || 0) + " remembered · " + ((page.d.memory || {}).inbox || 0) + " to review" }
                Line { k: "missions"; v: ((page.d.missions || {}).total || 0) + " recent · " + JSON.stringify((page.d.missions || {}).byStatus || {}) }
            }

            Card {
                title: "HOME LAUNCHER LOG"; source: "$XDG_RUNTIME_DIR/apvis-home-attempts.log"
                width: grid.width
                Repeater {
                    model: page.d.launcher || []
                    delegate: Text { required property var modelData; width: parent.width; elide: Text.ElideRight
                                     text: modelData; color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 10 }
                }
                Text { visible: (page.d.launcher || []).length === 0; text: "No launcher log in this session (development run)."
                       color: Theme.muted; font.pixelSize: 11 }
            }
        }
    }
}
