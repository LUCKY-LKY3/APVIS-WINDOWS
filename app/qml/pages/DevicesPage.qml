import QtQuick
import QtQuick.Controls
import "../theme"

// Devices: what this computer is and what it is connected to, read from the
// machine (DMI, /proc, /sys, psutil, the display server). Nothing illustrative.
Item {
    id: page
    readonly property var dev: shell.devices || ({})
    readonly property var host: dev.host || shell.host || ({})
    readonly property var route: shell.route || ({})
    readonly property var remote: ((shell.control || {}).state || {}).remote || ({})
    onVisibleChanged: if (visible) { shell.refreshDevices(); shell.refreshControl(); entry.restart() }
    Component.onCompleted: if (visible) { shell.refreshDevices(); shell.refreshControl() }
    property real reveal: 1
    NumberAnimation { id: entry; target: page; property: "reveal"; from: 0; to: 1; duration: 800; easing.type: Easing.OutCubic }

    component Kv: Item {
        property string k: ""
        property string v: ""
        property color vc: Theme.text
        visible: v.length > 0
        width: parent ? parent.width : 300; height: visible ? 30 : 0
        Text { anchors.verticalCenter: parent.verticalCenter; text: parent.k; color: Theme.muted; font.pixelSize: 12 }
        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.68; horizontalAlignment: Text.AlignRight
               elide: Text.ElideRight; text: parent.v; color: parent.vc; font.pixelSize: 13 }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line; opacity: 0.6 }
    }

    PageHeader {
        id: header
        width: parent.width
        code: "08"; title: "DEVICES"; reveal: page.reveal
        subtitle: "What this computer is and what it's connected to, read from the machine itself."
        HudButton { width: 120; caption: "Refresh"; glyph: "restart"; onClicked: { shell.refreshDevices(); shell.refreshControl() } }
    }
    Flickable {
        anchors.top: header.bottom; anchors.topMargin: 16; anchors.bottom: parent.bottom
        width: parent.width; contentHeight: grid.height + 10; clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: HudScrollBar {}
        Flow {
            id: grid
            width: parent.width - 12; spacing: 14
            readonly property real half: (width - spacing) / 2

            HudPanel {
                width: grid.half; reveal: page.reveal; order: 0
                title: "THIS COMPUTER"; glyph: "device"; meta: "ONLINE"
                Row {
                    spacing: 18
                    ApvisMark { width: 54; height: 48; glow: 0.5 }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        Text { text: page.host.model || page.host.hostname || "This computer"; color: Theme.text; font.pixelSize: 20; font.weight: Font.Light }
                        Text { text: (page.host.user || "") + "@" + (page.host.hostname || ""); color: Theme.accent; font.pixelSize: 12; font.family: Theme.monoFont }
                    }
                }
                Column {
                    width: parent.width
                    Kv { k: "System"; v: page.host.os || "" }
                    Kv { k: "Processor"; v: (page.host.cpu || "") + (page.host.cores ? "  ·  " + page.host.cores + " cores / " + page.host.threads + " threads" : "") }
                    Kv { k: "Graphics"; v: page.host.gpu || "" }
                    Kv { k: "Memory"; v: page.host.memoryGb ? page.host.memoryGb + " GiB" : "" }
                    Kv { k: "Kernel"; v: page.host.kernel || "" }
                    Kv { k: "Packages"; v: page.host.packages ? page.host.packages + " (dpkg)" : "" }
                }
            }
            HudPanel {
                width: grid.half; reveal: page.reveal; order: 1
                title: "DISPLAYS"; glyph: "screen"; meta: Qt.application.screens.length + " CONNECTED"
                Repeater {
                    model: Qt.application.screens
                    delegate: Item {
                        required property var modelData
                        required property int index
                        width: parent.width; height: 58
                        Rectangle { width: 64; height: 40; radius: 4; anchors.verticalCenter: parent.verticalCenter; color: "transparent"; border.color: Theme.accent
                                    Text { anchors.centerIn: parent; text: index + 1; color: Theme.accent; font.pixelSize: 16 } }
                        Column {
                            x: 80; anchors.verticalCenter: parent.verticalCenter
                            Text { text: modelData.name || ("Display " + (index + 1)); color: Theme.text; font.pixelSize: 14 }
                            Text { text: Math.round(modelData.width * modelData.devicePixelRatio) + " × " + Math.round(modelData.height * modelData.devicePixelRatio) +
                                         (modelData.devicePixelRatio !== 1 ? "  ·  scale " + modelData.devicePixelRatio : "") +
                                         (modelData.manufacturer ? "  ·  " + modelData.manufacturer + " " + (modelData.model || "") : "")
                                   color: Theme.muted; font.pixelSize: 12 }
                        }
                    }
                }
                HudButton { width: 180; glyph: "screen"; caption: "Display settings"; onClicked: shell.launch("displays") }
            }
            HudPanel {
                width: grid.half; reveal: page.reveal; order: 2
                title: "STORAGE"; glyph: "storage"; meta: (page.dev.storage || []).length + " MOUNTED"
                Repeater {
                    model: page.dev.storage || []
                    delegate: Column {
                        required property var modelData
                        width: parent.width; spacing: 5
                        Item {
                            width: parent.width; height: 20
                            Text { text: modelData.mount + "   " + modelData.device; color: Theme.text; font.pixelSize: 13; elide: Text.ElideRight; width: parent.width * 0.6 }
                            Text { anchors.right: parent.right; text: modelData.usedGb + " / " + modelData.totalGb + " GB  ·  " + modelData.fs; color: Theme.muted; font.pixelSize: 12 }
                        }
                        Rectangle { width: parent.width; height: 5; radius: 2.5; color: Theme.sheen(0.07)
                            Rectangle { height: parent.height; radius: 2.5; width: parent.width * modelData.pct / 100; color: modelData.pct >= 90 ? Theme.attention : Theme.accent } }
                    }
                }
                Text { visible: !(page.dev.storage || []).length; text: "Reading…"; color: Theme.muted; font.pixelSize: 12 }
            }
            HudPanel {
                width: grid.half; reveal: page.reveal; order: 3
                title: "NETWORK"; glyph: "wifi"
                Repeater {
                    model: page.dev.network || []
                    delegate: Item {
                        required property var modelData
                        width: parent.width; height: 44
                        Rectangle { width: 9; height: 9; radius: 4.5; anchors.verticalCenter: parent.verticalCenter; color: modelData.up ? Theme.accent : Theme.muted }
                        Column {
                            x: 22; anchors.verticalCenter: parent.verticalCenter
                            Text { text: modelData.kind + "  ·  " + modelData.name; color: Theme.text; font.pixelSize: 13 }
                            Text { text: (modelData.up ? "Up" : "Down") + (modelData.speedMbps ? "  ·  " + modelData.speedMbps + " Mb/s" : "") +
                                         (modelData.ipv4.length ? "  ·  " + modelData.ipv4.join(", ") : "")
                                   color: Theme.muted; font.pixelSize: 12 }
                        }
                    }
                }
                Text { visible: !(page.dev.network || []).length; text: "Reading…"; color: Theme.muted; font.pixelSize: 12 }
                HudButton { width: 180; glyph: "wifi"; caption: "Network settings"; onClicked: shell.launch("network") }
            }
            HudPanel {
                width: grid.half; reveal: page.reveal; order: 4
                title: "LOCAL AI"; glyph: "brain"; meta: page.route.reachable ? "ONLINE" : "NOT REACHABLE"
                metaColour: page.route.reachable ? Theme.accent : Theme.attention
                Column {
                    width: parent.width
                    Kv { k: "Where"; v: page.route.thisDevice ? "This computer" : (page.route.host || "") }
                    Kv { k: "Ollama"; v: page.route.version || (page.route.reachable ? "" : "—") }
                    Kv { k: "Fast model"; v: page.route.model || "" }
                    Kv { k: "Privacy"; v: "Local only"; vc: Theme.accent }
                }
                HudButton { width: 180; glyph: "brain"; caption: "Local AI settings"; onClicked: shell.pageRequested("settings") }
            }
            HudPanel {
                width: grid.half; reveal: page.reveal; order: 5
                title: "REMOTE ACCESS"; glyph: "key"
                meta: !page.remote.available ? "" : page.remote.on ? "ON" : "OFF"
                metaColour: page.remote.on ? Theme.warm : Theme.muted
                Text { width: parent.width; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 13
                       text: !page.remote.available ? (page.remote.detail || "Checking…") :
                             (page.remote.on ? "Remote access is on" : "Remote access is off") + "  ·  " + (page.remote.keys || 0) + " trusted key" + (page.remote.keys === 1 ? "" : "s") }
                Text { visible: !!page.remote.on && (page.remote.addresses || []).length > 0; color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 12
                       text: "ssh apvis@" + (page.remote.addresses || []).join("   ssh apvis@") }
                Text { width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 11
                       text: "Computers you trust are the keys in ~/.ssh/authorized_keys. Switch remote access on or off in Settings." }
            }
        }
    }
}
