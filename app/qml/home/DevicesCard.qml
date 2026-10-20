import QtQuick
import "../theme"

// DEVICES (owner concept): what this computer is connected to, all measured —
// this computer, the local AI host, and the network. Opens the Devices page.
GlassCard {
    id: card
    title: "DEVICES"
    signal go(string key)
    onOpened: go("devices")
    readonly property var host: shell.host || ({})
    readonly property var sys: shell.system || ({})
    readonly property var route: shell.route || ({})
    readonly property bool wifi: !!(sys.wifi && sys.wifi.connected)

    component DeviceRow: Item {
        id: d
        property string glyph: "device"
        property string name: ""
        property string detail: ""
        property bool ok: true
        width: parent ? parent.width : 300; height: 50
        Glyph { anchors.verticalCenter: parent.verticalCenter; width: 22; height: 22; kind: d.glyph; stroke: Theme.text; opacity: 0.85 }
        Column {
            x: 38; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 38; spacing: 2
            Text { width: parent.width; text: d.name; color: Theme.text; font.pixelSize: 14; elide: Text.ElideRight }
            Text { text: d.detail; color: d.ok ? Theme.accent : Theme.attention; font.pixelSize: 12 }
        }
    }
    spacing: 2
    DeviceRow {
        glyph: "device"
        name: (card.host.model || card.host.hostname || "This computer") + "  (This device)"
        detail: "Online"
    }
    DeviceRow {
        glyph: "brain"
        name: card.route.thisDevice || !card.route.host ? "Local AI · Ollama" : "AI host · " + card.route.host
        detail: card.route.reachable ? "Online" + (card.route.model ? " · " + card.route.model : "") :
               card.route.checking ? "Checking…" : "Not reachable"
        ok: !!card.route.reachable
    }
    DeviceRow {
        glyph: card.wifi ? "wifi" : "wired"
        name: card.wifi ? "Wi-Fi · " + card.sys.wifi.ssid : "Network"
        detail: card.wifi ? "Connected" + (card.sys.wifi.signal ? " · " + card.sys.wifi.signal + "%" : "") :
               card.sys.wired ? "Ethernet connected" : card.sys.wired === false ? "Not connected" : "Checking…"
        ok: card.wifi || !!card.sys.wired
    }
    Rectangle { width: parent.width; height: 1; color: Theme.line; opacity: 0.8 }
    Item {
        width: parent.width; height: 40
        Text { anchors.verticalCenter: parent.verticalCenter; text: "Manage devices"; color: Theme.text; font.pixelSize: 14 }
        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: "›"; color: Theme.muted; font.pixelSize: 18 }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: card.go("devices") }
    }
}
