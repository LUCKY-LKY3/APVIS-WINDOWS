import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "../theme"

// The menu bar (owner concept): APVIS mark and menus on the left, real status
// on the right (network, volume, battery when there is one, date and time).
// Menu choices are emitted as action keys; Home carries them out.
Item {
    id: bar
    property string openMenu: ""
    property date now: new Date()
    property bool powerOpen: false
    signal action(string key)
    height: 40
    readonly property bool app: typeof windowsApp !== "undefined" && windowsApp
    readonly property var ai: (typeof shell.aiStatus !== "undefined" && shell.aiStatus) ? shell.aiStatus : ({})

    readonly property var sys: shell.system || ({})
    readonly property var menus: ({
        "System": [["About this computer", "page:devices", ""], ["System monitor", "page:system", ""], ["Control Centre", "control", ""],
                   ["-"], ["Displays", "launch:displays", ""], ["Sound", "launch:sound", ""], ["Network", "launch:network", ""],
                   ["-"], ["Keyboard shortcuts", "keys", "F1"],
                   ...(shell.guest ? [["Log out…", "power", ""]]          // Guest (V4): no lock, no restart or shut down
                                   : [["Lock", "lock", "Win+L"], ["Sleep, restart or shut down…", "power", ""]])],
        "Apps": [["All apps", "launch:apps", "Win+Space"], ["APVIS Browser", "launch:browser", "Win+B"], ["Files", "launch:files", "Win+E"], ["Terminal", "launch:terminal", "Ctrl+Alt+T"],
                 ["Text editor", "launch:editor", ""], ["-"], ["Search this computer", "search", "Ctrl+K"]],
        // The APVIS logo's menu (owner, V4): Home, then every app that is open.
        "Windows": [["APVIS Home", "page:", "Win+D"], ["-"]].concat(
            !shell.windowsAvailable ? [["Open apps need the APVIS 4 image", "", ""]]
            : (shell.openWindows || []).length === 0 ? [["No other apps are open", "", ""]]
            : shell.openWindows.map((w, i) => [w.title, "window:" + i, w.app])),
        "APVIS": [["Ask APVIS", "ask", ""], ["What was I doing?", "continuity", ""], ["-"], ["Automation", "page:missions", ""],
                  ["Memory", "page:notes", ""], ["Intelligence", "page:atlas", ""], ["-"], ["Check for updates", "updates", ""]]
    })

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.shade(0.85) }
            GradientStop { position: 1; color: Theme.shade(0.55) }
        }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 0.7) }

    Row {
        id: left
        x: 18; height: parent.height; spacing: 26
        // The logo alone, as a button: back to Home from anywhere (owner, 2026-10-09).
        AbstractButton {
            id: logoButton
            width: 30; height: 30; anchors.verticalCenter: parent.verticalCenter
            Accessible.name: "APVIS Home and open apps"
            onClicked: {
                if (bar.app) { bar.action("page:"); return }
                if (bar.openMenu === "Windows") { bar.openMenu = ""; return }
                shell.refreshWindows()
                bar.openMenu = "Windows"
            }
            background: Rectangle { radius: 15; color: logoButton.hovered ? Theme.sheen(0.07) : "transparent"
                                    border.width: logoButton.visualFocus ? 1.5 : 0; border.color: Theme.text }
            contentItem: ApvisMark { glow: logoButton.hovered ? 1.0 : 0.5 }
        }
        Text { visible: bar.app; anchors.verticalCenter: parent.verticalCenter; text: "APVIS"; color: Theme.text
               font.pixelSize: 15; font.letterSpacing: 4; font.weight: Font.Medium }
        Text { visible: bar.app; anchors.verticalCenter: parent.verticalCenter; text: "//   INTELLIGENCE STAGE"; color: Theme.muted
               font.pixelSize: 12; font.letterSpacing: 2.4 }
        Repeater {
            model: bar.app ? [] : ["System", "Apps", "APVIS", "Settings"]
            delegate: AbstractButton {
                id: menuTitle
                required property string modelData
                readonly property bool open: bar.openMenu === modelData
                height: 28; width: menuText.implicitWidth + 16; anchors.verticalCenter: parent.verticalCenter
                Accessible.name: modelData + " menu"
                onClicked: {
                    if (modelData === "Settings") { bar.openMenu = ""; bar.action("page:settings"); return }
                    bar.openMenu = open ? "" : modelData
                }
                // Moving across the bar while a menu is open switches menus, like a desktop menu bar.
                onHoveredChanged: if (hovered && bar.openMenu !== "" && modelData !== "Settings") bar.openMenu = modelData
                background: Rectangle { radius: 6; color: menuTitle.open ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.14) :
                                                           menuTitle.hovered ? Theme.sheen(0.06) : "transparent"
                                        border.width: menuTitle.visualFocus ? 1.5 : 0; border.color: Theme.text }
                contentItem: Text { id: menuText; text: menuTitle.modelData; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                    color: menuTitle.open || menuTitle.hovered ? Theme.text : Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, 0.72)
                                    font.pixelSize: 14 }
            }
        }
    }

    Row {
        id: right
        anchors.right: parent.right; anchors.rightMargin: 14; height: parent.height; spacing: 18
        // APVIS for Windows: live readings as header chips.
        Repeater {
            model: bar.app ? [["CPU", bar.sys.cpu !== undefined && bar.sys.cpu !== null ? Math.round(bar.sys.cpu) + "%" : "—"],
                              ["RAM", bar.sys.memory !== undefined && bar.sys.memory !== null ? Math.round(bar.sys.memory) + "%" : "—"],
                              ["GPU", (shell.game || {}).gpu && shell.game.gpu.temp !== null ? shell.game.gpu.temp + "°C" : "—"]] : []
            delegate: Row {
                required property var modelData
                anchors.verticalCenter: parent.verticalCenter; spacing: 6
                Text { anchors.verticalCenter: parent.verticalCenter; text: modelData[0]; color: Theme.accent; font.pixelSize: 10; font.letterSpacing: 1.6 }
                Text { anchors.verticalCenter: parent.verticalCenter; text: modelData[1]; color: Theme.text; font.pixelSize: 12; font.family: Theme.monoFont }
            }
        }
        Rectangle { visible: bar.app; anchors.verticalCenter: parent.verticalCenter; width: 1; height: 16; color: Theme.line }
        // APVIS for Windows: where Ask runs right now (graphics card, or light mode while gaming).
        Row {
            visible: bar.app
            anchors.verticalCenter: parent.verticalCenter; spacing: 7
            readonly property string mode: bar.ai.mode || ((shell.route || {}).reachable ? "gpu" : "off")
            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 7; height: 7; radius: 3.5
                        color: parent.mode === "gpu" ? Theme.signal : parent.mode === "light" ? Theme.attention : Theme.muted }
            Text { anchors.verticalCenter: parent.verticalCenter; color: Theme.muted; font.pixelSize: 12
                   text: (bar.ai.model || (shell.route || {}).model || "Local AI offline") + (parent.mode === "light" ? "  ·  light mode" : "") }
        }
        Text { visible: bar.app; anchors.verticalCenter: parent.verticalCenter; color: Theme.muted; font.pixelSize: 12; font.family: Theme.monoFont
               text: Qt.formatDateTime(new Date(bar.now.getTime() + bar.now.getTimezoneOffset() * 60000), "HH:mm") + "Z" }
        // Network: Wi-Fi when joined, wired when plugged in, dim when neither.
        Glyph {
            visible: !bar.app
            anchors.verticalCenter: parent.verticalCenter; width: 17; height: 17
            readonly property bool wifi: !!(bar.sys.wifi && bar.sys.wifi.connected)
            kind: wifi ? "wifi" : "wired"
            stroke: wifi || bar.sys.wired ? Theme.text : Theme.muted
            opacity: wifi || bar.sys.wired ? 1 : 0.5
            ToolTip.visible: netMouse.containsMouse
            ToolTip.text: wifi ? "Wi-Fi · " + bar.sys.wifi.ssid : bar.sys.wired ? "Wired network" : "Not connected"
            MouseArea { id: netMouse; anchors.fill: parent; hoverEnabled: true; onClicked: bar.action("control") }
        }
        Item {
            visible: !bar.app
            anchors.verticalCenter: parent.verticalCenter
            width: volRow.width; height: 24
            Row {
                id: volRow
                anchors.verticalCenter: parent.verticalCenter; spacing: 6
                Glyph { width: 17; height: 17; kind: "volume"; stroke: bar.sys.muted ? Theme.muted : Theme.text; anchors.verticalCenter: parent.verticalCenter }
                Text { visible: bar.sys.volume !== undefined && bar.sys.volume !== null; anchors.verticalCenter: parent.verticalCenter
                       text: bar.sys.muted ? "Muted" : bar.sys.volume + "%"; color: Theme.text; font.pixelSize: 13 }
            }
            MouseArea { anchors.fill: parent; onClicked: bar.action("control") }
        }
        Row {
            visible: !!bar.sys.battery
            anchors.verticalCenter: parent.verticalCenter; spacing: 6
            Glyph { width: 19; height: 19; kind: "battery"; stroke: bar.sys.battery && bar.sys.battery.percent < 15 ? Theme.attention : Theme.text
                    anchors.verticalCenter: parent.verticalCenter }
            Text { anchors.verticalCenter: parent.verticalCenter; color: Theme.text; font.pixelSize: 13
                   text: bar.sys.battery ? bar.sys.battery.percent + "%" + (bar.sys.battery.plugged ? " ⚡" : "") : "" }
        }
        // Local weather (Settings -> Appearance -> Weather); hidden until a town is set.
        Text { visible: !!bar.sys.weather; anchors.verticalCenter: parent.verticalCenter; color: Theme.text; font.pixelSize: 14
               text: bar.sys.weather ? bar.sys.weather.symbol + " " + bar.sys.weather.temp + "°" : ""
               ToolTip.visible: wxHover.containsMouse
               ToolTip.text: bar.sys.weather ? bar.sys.weather.label + ": " + bar.sys.weather.words + ", feels like " + bar.sys.weather.feels + "°C" : ""
               MouseArea { id: wxHover; anchors.fill: parent; hoverEnabled: true } }
        Text { anchors.verticalCenter: parent.verticalCenter; text: Qt.formatDateTime(bar.now, "ddd d MMM"); color: Theme.text; font.pixelSize: 14 }
        Text { anchors.verticalCenter: parent.verticalCenter; text: Qt.formatDateTime(bar.now, "HH:mm"); color: Theme.text; font.pixelSize: 14; font.weight: Font.Medium }
        // APVIS for Windows: minimise (the power button closes the app).
        AbstractButton {
            id: minButton
            visible: bar.app
            width: 30; height: 28; anchors.verticalCenter: parent.verticalCenter
            Accessible.name: "Minimise APVIS"
            onClicked: bar.Window.window.showMinimized()
            background: Rectangle { radius: 6; color: minButton.hovered ? Theme.sheen(0.07) : "transparent" }
            contentItem: Item { Rectangle { anchors.centerIn: parent; width: 12; height: 1.5; color: Theme.text } }
        }
        AbstractButton {
            id: powerButton
            width: 30; height: 28; anchors.verticalCenter: parent.verticalCenter
            Accessible.name: "Power menu"
            onClicked: bar.action("power")
            background: Rectangle { radius: 6; color: bar.powerOpen ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.16) :
                                                       powerButton.hovered ? Theme.sheen(0.07) : "transparent"
                                    border.width: powerButton.visualFocus ? 1.5 : 0; border.color: Theme.text }
            contentItem: Item { Glyph { anchors.centerIn: parent; width: 16; height: 16; kind: "power"; stroke: bar.powerOpen ? Theme.accent : Theme.text } }
        }
    }

    // ---- the open menu
    Item {
        id: dropdown
        visible: bar.openMenu !== "" && opacity > 0.01
        opacity: bar.openMenu !== "" ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        readonly property Item anchorItem: {
            if (bar.openMenu === "Windows") return logoButton
            for (let i = 0; i < left.children.length; ++i) {
                const ch = left.children[i]
                if (ch.modelData === bar.openMenu) return ch
            }
            return null
        }
        x: left.x + (anchorItem ? anchorItem.x : 0) - 6
        y: bar.height + 4
        width: 280; height: menuCol.height + 16
        Chamfer { anchors.fill: parent; cut: 12; fill: Theme.panel; fillOpacity: 0.97; fill2: Theme.bgBottom; fill2Opacity: 0.97
                  stroke: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.35); edgeGlow: true }
        Column {
            id: menuCol
            x: 8; y: 8; width: parent.width - 16
            Repeater {
                model: bar.openMenu ? bar.menus[bar.openMenu] || [] : []
                delegate: Item {
                    id: entry
                    required property var modelData
                    readonly property bool separator: modelData[0] === "-"
                    width: menuCol.width; height: separator ? 9 : 34
                    Rectangle { visible: entry.separator; anchors.centerIn: parent; width: parent.width - 16; height: 1; color: Theme.line }
                    Rectangle {
                        visible: !entry.separator
                        anchors.fill: parent; radius: 6
                        color: entryMouse.containsMouse ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.14) : "transparent"
                        Text { x: 12; anchors.verticalCenter: parent.verticalCenter; text: entry.modelData[0]; font.pixelSize: 13
                               width: parent.width - 24 - (hint.text ? hint.implicitWidth + 12 : 0); elide: Text.ElideRight
                               color: entry.modelData[1] ? Theme.text : Theme.muted }
                        Text { id: hint; anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                               text: entry.modelData[2] || ""; color: Theme.muted; font.pixelSize: 11; font.family: Theme.monoFont
                               width: Math.min(implicitWidth, 110); elide: Text.ElideRight }
                        MouseArea { id: entryMouse; anchors.fill: parent; hoverEnabled: true; enabled: !!entry.modelData[1]; cursorShape: Qt.PointingHandCursor
                                    onClicked: { const key = entry.modelData[1]; bar.openMenu = ""; bar.action(key) } }
                    }
                }
            }
        }
    }
}
