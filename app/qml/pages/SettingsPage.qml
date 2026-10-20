import QtQuick
import QtQuick.Controls
import "../theme"
import "../controls"

// Settings: every value shown is read from the system, and every change is
// read back (see apvis_os.control). A section rail on the left jumps to each
// panel; the overview at the top shows the live state of the whole machine.
Item {
    id: page
    readonly property var s: shell.settings || ({})
    readonly property var ctl: (shell.control || {}).state || ({})
    readonly property var remote: ctl.remote || ({})
    readonly property var powerCfg: ctl.power || ({})
    readonly property var u: shell.updates || ({})
    readonly property var sys: shell.system || ({})
    readonly property var tel: shell.telemetry || ({})
    readonly property var route: shell.route || ({})
    readonly property var render: shell.render || ({})
    readonly property bool navShown: width >= 1050
    readonly property bool wide: flick.width >= 900
    function focusFirst() { ollamaField.forceActiveFocus() }
    onVisibleChanged: if (visible) { shell.refreshControl(); shell.refreshModels(); entry.restart() }
    Component.onCompleted: if (visible) { shell.refreshControl(); shell.refreshModels() }
    Timer { interval: 5000; repeat: true; running: page.visible; onTriggered: { shell.refreshControl(); page.now = Date.now() } }
    property real now: Date.now()

    property real reveal: 1
    NumberAnimation { id: entry; target: page; property: "reveal"; from: 0; to: 1; duration: 800; easing.type: Easing.OutCubic }

    component Note: Text {
        width: parent ? parent.width : 200; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 12; lineHeight: 1.1
    }
    component Label: Text {
        color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 1.6 : 0.3; topPadding: 2
    }
    component Kv: Item {
        property string k: ""
        property string v: ""
        property color vColour: Theme.text
        width: parent ? parent.width : 240; height: 28
        Text { anchors.verticalCenter: parent.verticalCenter; text: parent.k; color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 1.4 : 0.3 }
        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: parent.v; color: parent.vColour
               font.family: Theme.monoFont; font.pixelSize: 11; elide: Text.ElideLeft; width: Math.min(implicitWidth, parent.width * 0.7); horizontalAlignment: Text.AlignRight }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line; opacity: 0.5 }
    }
    // A status light with a word, used in the overview.
    component StatusChip: Item {
        property string label: ""
        property string value: ""
        property color tone: Theme.accent
        property string glyph: "core"
        width: parent ? (parent.width - 10) / 2 : 180; height: 50
        Chamfer { anchors.fill: parent; cut: 8; fill: Theme.bgBottom; fillOpacity: 0.55; stroke: Qt.rgba(tone.r, tone.g, tone.b, 0.45) }
        Rectangle { x: 12; anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: parent.tone
                    Rectangle { anchors.centerIn: parent; width: 18; height: 18; radius: 9; color: parent.color; opacity: 0.18 } }
        Column {
            x: 30; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 40; spacing: 2
            Text { text: parent.parent.label; color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 9; font.letterSpacing: Theme.caps ? 1.5 : 0.3 }
            Text { width: parent.width; text: parent.parent.value; color: Theme.text; font.pixelSize: 12; elide: Text.ElideRight }
        }
    }

    PageHeader {
        id: header
        width: parent.width
        code: "05"; title: "SETTINGS"; reveal: page.reveal
        subtitle: "Everything here shows the real system state and checks each change."
    }

    // ---------------------------------------------------------------- section rail
    readonly property var sections: [["overview", "Overview", "home"], ["appearance", "Appearance", "screen"], ["power", "Power", "power"], ["ai", "Local AI", "brain"],
                                     ["remote", "Remote access", "key"], ["backup", "Backup", "storage"], ["updates", "Updates", "restart"],
                                     ["prefs", "Preferences", "settings"], ["system", "System", "device"], ["about", "About", "apvis"]]
    function sectionItem(key) {
        return ({ overview: overviewSec, appearance: appearanceSec, power: powerSec, ai: aiSec, remote: remoteSec, backup: backupSec, updates: updatesSec,
                  prefs: prefsSec, system: systemSec, about: aboutSec })[key]
    }
    property string current: "overview"
    property bool jumping: false
    function jump(key) {
        const item = sectionItem(key)
        if (!item) return
        current = key; jumping = true
        scroll.to = Math.max(0, Math.min(item.mapToItem(stack, 0, 0).y - 4, flick.contentHeight - flick.height))
        scroll.restart()
    }
    function followScroll() {
        if (jumping) return
        let best = "overview", bestY = -1e9
        for (const sec of sections) {
            const item = sectionItem(sec[0])
            const y = item.mapToItem(stack, 0, 0).y
            if (y <= flick.contentY + 80 && y > bestY) { best = sec[0]; bestY = y }
        }
        current = best
    }
    NumberAnimation { id: scroll; target: flick; property: "contentY"; duration: 420; easing.type: Easing.OutCubic
                      onStopped: page.jumping = false }

    Item {
        id: nav
        visible: page.navShown
        anchors.top: header.bottom; anchors.topMargin: 16
        width: 206; height: navCol.height + 24
        opacity: page.reveal
        transform: Translate { x: (1 - page.reveal) * -20 }
        Chamfer { anchors.fill: parent; cut: 14; fill: Theme.raised; fillOpacity: 0.7; fill2: Theme.bgBottom; fill2Opacity: 0.7
                  stroke: Theme.line; brackets: true; edgeGlow: true }
        Rectangle {
            id: navLight
            readonly property Item target: navRepeater.count ? navRepeater.itemAt(Math.max(0, page.sections.findIndex(x => x[0] === page.current))) : null
            x: 10; width: parent.width - 20; height: 36
            y: navCol.y + (target ? target.y : 0)
            radius: 3
            color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12)
            border.width: 1; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.5)
            Behavior on y { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
            Rectangle { x: 0; y: 8; width: 3; height: parent.height - 16; color: Theme.accent }
        }
        Column {
            id: navCol
            x: 10; y: 12; width: parent.width - 20; spacing: 2
            Repeater {
                id: navRepeater
                model: page.sections
                delegate: AbstractButton {
                    id: navItem
                    required property var modelData
                    readonly property bool active: page.current === modelData[0]
                    width: navCol.width; height: 36
                    Accessible.name: modelData[1]
                    onClicked: page.jump(modelData[0])
                    background: Rectangle { radius: 3; color: navItem.hovered && !navItem.active ? Theme.hover : "transparent"
                                            border.width: navItem.visualFocus ? 1.5 : 0; border.color: Theme.text
                                            Behavior on color { ColorAnimation { duration: 150 } } }
                    contentItem: Item {
                        Glyph { x: 14; anchors.verticalCenter: parent.verticalCenter; width: 15; height: 15; kind: navItem.modelData[2]
                                stroke: navItem.active ? Theme.accent : Theme.muted }
                        Text { x: 40; anchors.verticalCenter: parent.verticalCenter; text: navItem.modelData[1]
                               color: navItem.active || navItem.hovered ? Theme.text : Theme.muted; font.pixelSize: 13
                               Behavior on color { ColorAnimation { duration: 150 } } }
                        Rectangle {
                            anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                            width: 6; height: 6; radius: 3; color: Theme.attention
                            visible: (navItem.modelData[0] === "updates" && page.u.state === "available") ||
                                     (navItem.modelData[0] === "ai" && page.s.ollamaUp === false)
                        }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- panels
    Flickable {
        id: flick
        anchors.top: header.bottom; anchors.topMargin: 16; anchors.bottom: parent.bottom
        x: page.navShown ? nav.width + 16 : 0
        width: parent.width - x
        contentHeight: stack.height + 24
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: HudScrollBar {}
        onContentYChanged: page.followScroll()
        Column {
            id: stack
            width: flick.width - 14
            spacing: 14
            enabled: !shell.guest                // V4: Guest sees the settings but can't change them

            Rectangle {
                visible: !!shell.guest
                width: parent.width; height: guestNote.implicitHeight + 22; radius: 4
                color: Theme.tint(Theme.accent, 0.06); border.width: 1; border.color: Theme.tint(Theme.accent, 0.4)
                Text { id: guestNote; x: 16; y: 11; width: parent.width - 32; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 13
                       text: "You're using Guest: settings are shown here but can't be changed. Sign in as APVIS to change them." }
            }

            // ---- overview
            HudPanel {
                id: overviewSec
                width: parent.width; reveal: page.reveal; order: 0
                title: "SYSTEM OVERVIEW"; glyph: "home"
                meta: (page.sys.hostname || "").toUpperCase()
                Item {
                    width: parent.width
                    height: page.wide ? 126 : 126 + chips.height + 14
                    // Identity.
                    Row {
                        id: ident
                        spacing: 16
                        width: page.wide ? parent.width * 0.3 : parent.width * 0.45
                        Item {
                            width: 76; height: 76
                            Rectangle { anchors.fill: parent; radius: 38; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.07)
                                        border.width: 1; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.5) }
                            Rectangle { anchors.centerIn: parent; width: 60; height: 60; radius: 30; color: "transparent"
                                        border.width: 1; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.2) }
                            ApvisMark { anchors.centerIn: parent; width: 44; height: 44; glow: 0.8 }
                        }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter; spacing: 3
                            width: parent.width - 92
                            Text { text: Theme.label("APVIS OS"); color: Theme.text; font.pixelSize: 20; font.letterSpacing: 3; font.weight: Font.Light }
                            Text { width: parent.width; text: page.u.installed && page.u.installed !== "0" ? page.u.installed : (page.s.version || "development build"); color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 11; elide: Text.ElideRight }
                            Text { width: parent.width; elide: Text.ElideRight; color: Theme.muted; font.pixelSize: 11
                                   text: page.sys.boot_epoch_ms ? "Up " + (function () { const s = Math.floor((page.now - page.sys.boot_epoch_ms) / 1000)
                                         return Math.floor(s / 3600) + "h " + Math.floor(s % 3600 / 60) + "m" })() : "" }
                        }
                    }
                    // Live gauges.
                    Row {
                        id: gauges
                        x: page.wide ? ident.width + 10 : parent.width * 0.45
                        spacing: 6
                        RingGauge { width: 96; height: 96; label: "CPU"; value: page.sys.available ? page.sys.cpu : null }
                        RingGauge { width: 96; height: 96; label: "RAM"; value: page.sys.available ? page.sys.memory : null
                                    sub: page.tel.memoryUsedGb ? page.tel.memoryUsedGb + "/" + page.tel.memoryTotalGb + " GB" : "" }
                        RingGauge { width: 96; height: 96; label: "DISK"; value: page.sys.available && page.sys.disk !== null ? page.sys.disk : null }
                    }
                    // Status chips.
                    Flow {
                        id: chips
                        x: page.wide ? gauges.x + gauges.width + 18 : 0
                        y: page.wide ? 4 : 140
                        width: parent.width - x
                        spacing: 10
                        StatusChip { label: "LOCAL AI"; glyph: "brain"
                                     value: page.route.reachable ? (page.route.model || "Ollama") + " · ready" : page.route.checking ? "Checking…" : "Not reachable"
                                     tone: page.route.reachable ? Theme.accent : Theme.attention }
                        StatusChip { label: "UPDATES"
                                     value: page.u.state === "available" ? (page.u.latest || "") + " available" : page.u.state === "current" ? "Up to date" :
                                            page.u.state === "error" ? "Couldn't check" : "Not checked yet"
                                     tone: page.u.state === "available" ? Theme.attention : page.u.state === "current" ? Theme.accent : Theme.muted }
                        StatusChip { label: "REMOTE ACCESS"
                                     value: !page.remote.available ? "Not installed" : page.remote.on ? "On · " + (page.remote.keys || 0) + " key(s)" : "Off"
                                     tone: page.remote.on ? Theme.warm : Theme.muted }
                        StatusChip { label: "GRAPHICS"
                                     value: page.render.software ? "CPU renderer" : (page.render.renderer === "sphere3d" ? "GPU · 3D" : "GPU · 2D") +
                                            ((shell.frameInfo || {}).fps !== undefined ? " · " + shell.frameInfo.fps + " fps" : "")
                                     tone: page.render.software ? Theme.attention : Theme.accent }
                    }
                }
            }

            Flow {
                id: lanes
                width: parent.width
                spacing: 14
                readonly property real laneWidth: page.wide ? (width - spacing) / 2 : width

                // ================================ left lane
                Column {
                    width: lanes.laneWidth; spacing: 14

                    HudPanel {
                        id: appearanceSec
                        width: parent.width; reveal: page.reveal; order: 1
                        title: "APPEARANCE"; glyph: "screen"
                        Label { text: Theme.label("ACCENT COLOUR") }
                        Row {
                            spacing: 12
                            Repeater {
                                model: [["neural", Theme.accents["neural"].accent, "Neural Fabric (APVIS 7 blue)"], ["lacquer", Theme.accents["lacquer"].accent, "Lacquer and brass"], ["apvis", Theme.accents["apvis"].accent, "APVIS green (V2)"], ["emerald", Theme.accents["emerald"].accent, "Emerald"], ["aqua", Theme.accents["aqua"].accent, "Aqua"],
                                        ["cyan-steel", Theme.accents["cyan-steel"].accent, "Cyan steel"], ["emerald-silver", Theme.accents["emerald-silver"].accent, "Emerald silver"], ["cool-white", Theme.accents["cool-white"].accent, "Cool white"]]
                                delegate: AbstractButton {
                                    id: swatch
                                    required property var modelData
                                    readonly property bool chosen: (page.render.accent || "apvis") === modelData[0]
                                    width: 34; height: 34
                                    Accessible.name: modelData[2] + (chosen ? ", chosen" : "")
                                    ToolTip.visible: hovered; ToolTip.text: modelData[2]
                                    onClicked: shell.setAccent(modelData[0])
                                    background: Item {
                                        Rectangle { anchors.centerIn: parent; width: 34; height: 34; radius: 17; color: "transparent"
                                                    border.width: swatch.chosen || swatch.visualFocus ? 2 : 0; border.color: Theme.text }
                                        Rectangle { anchors.centerIn: parent; width: 24; height: 24; radius: 12; color: swatch.modelData[1]
                                                    border.width: swatch.modelData[0] === "emerald-silver" ? 3 : 0; border.color: Theme.accents["emerald-silver"].muted }
                                    }
                                }
                            }
                        }
                        // Glass/HUD panels belong to the V2 looks; lacquer has its own panels.
                        Label { visible: !Theme.lacquer; text: Theme.label("PANEL STYLE") }
                        Segmented {
                            visible: !Theme.lacquer
                            options: ["glass", "hud"]
                            value: page.render.style || "glass"
                            label: v => v === "glass" ? "Glass (rounded)" : "HUD (cut corners)"
                            onPicked: v => shell.setStyle(v)
                        }
                        Note { text: Theme.lacquer ? "Lacquer and brass is the APVIS look. Changes apply straight away and are remembered."
                                                   : "Glass is the APVIS concept look. Changes apply straight away and are remembered." }
                        Label { text: Theme.label("WEATHER") }
                        Row {
                            width: parent.width; spacing: 8
                            TextField {
                                id: townField
                                width: parent.width - 106; height: 38
                                Component.onCompleted: text = ((page.s.weather || {}).place || "").split(",")[0]
                                placeholderText: "Your town, e.g. London (empty = weather off)"; placeholderTextColor: Theme.muted
                                color: Theme.text; selectByMouse: true; font.pixelSize: 13; verticalAlignment: TextInput.AlignVCenter; leftPadding: 12
                                Accessible.name: "Weather town"
                                background: Chamfer { cut: 8; fill: Theme.bgBottom; fillOpacity: 0.6
                                                      stroke: townField.activeFocus ? Theme.accent : Theme.line; strokeWidth: townField.activeFocus ? 1.5 : 1 }
                                onAccepted: shell.setWeatherTown(text)
                            }
                            HudButton { width: 98; caption: "Save"; tone: "primary"; onClicked: shell.setWeatherTown(townField.text) }
                        }
                        Note {
                            readonly property var r: (page.s.weather || {}).reading
                            text: page.s.weatherMessage ? page.s.weatherMessage + (r ? "  Now: " + r.symbol + " " + r.temp + "°C, " + r.words + "." : "")
                                  : r ? r.label + ": " + r.symbol + " " + r.temp + "°C, " + r.words + " (Open-Meteo, refreshed every 30 minutes)."
                                  : "Shows the temperature in the top bar and answers \"what's the weather?\" from Open-Meteo (no account needed)."
                        }
                    }

                    HudPanel {
                        id: powerSec
                        width: parent.width; reveal: page.reveal; order: 1
                        title: "POWER"; glyph: "power"
                        PowerButtons { buttonWidth: Math.min(130, (parent.width - 18) / 4) }
                        Label { text: Theme.label("SCREEN OFF AFTER") }
                        Segmented {
                            options: page.powerCfg.screenChoices || [0, 2, 5, 10, 15, 30]
                            value: page.powerCfg.screenOff === undefined ? 10 : page.powerCfg.screenOff
                            label: v => v === 0 ? "Never" : v + " min"
                            onPicked: minutes => shell.setPowerTimers(minutes, page.powerCfg.sleep || 0)
                        }
                        Label { text: Theme.label("SLEEP AFTER") }
                        Segmented {
                            options: page.powerCfg.sleepChoices || [0, 15, 30, 60, 120]
                            value: page.powerCfg.sleep || 0
                            label: v => v === 0 ? "Never" : v + " min"
                            onPicked: minutes => shell.setPowerTimers(page.powerCfg.screenOff === undefined ? 10 : page.powerCfg.screenOff, minutes)
                        }
                        Note { text: (shell.control || {}).message || "Restart, shut down and sleep ask for a second press." }
                    }

                    HudPanel {
                        id: remoteSec
                        width: parent.width; reveal: page.reveal; order: 3
                        title: "REMOTE ACCESS  ·  SSH"; glyph: "key"
                        tint: page.remote.on ? Theme.warm : Theme.accent
                        meta: !page.remote.available ? "" : page.remote.on ? "LISTENING" : "OFF"
                        metaColour: page.remote.on ? Theme.warm : Theme.muted
                        Text { visible: !page.remote.available; width: parent.width; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 13
                               text: page.remote.detail || "Checking…" }
                        HudToggle {
                            visible: !!page.remote.available
                            width: parent.width
                            on: !!page.remote.on
                            caption: "Allow remote access"
                            detail: (page.remote.keys || 0) + ((page.remote.keys === 1) ? " key" : " keys") + " authorised on this computer"
                            onClicked: shell.setRemoteAccess(!page.remote.on)
                        }
                        Rectangle {
                            visible: !!page.remote.on && (page.remote.addresses || []).length > 0
                            width: parent.width; height: addr.height + 16; radius: 4
                            color: Theme.shade(0.35); border.width: 1; border.color: Theme.line
                            Text { id: addr; x: 12; y: 8; width: parent.width - 24; wrapMode: Text.WrapAnywhere
                                   color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 12
                                   text: "$ ssh apvis@" + (page.remote.addresses || []).join("\n$ ssh apvis@") }
                        }
                        Note { text: "Keys only (passwords never work) and home-network addresses only. To let a computer in, add its public key " +
                                     "to ~/.ssh/authorized_keys. It stays on after a restart until you turn it off." }
                    }

                    HudPanel {
                        id: prefsSec
                        width: parent.width; reveal: page.reveal; order: 5
                        title: "PREFERENCES"; glyph: "settings"
                        HudToggle { width: parent.width; on: !!page.s.dnd; caption: "Do not disturb"
                                    detail: page.s.dndNote || "Hides notifications. Approvals always get through."
                                    onClicked: shell.setDoNotDisturb(!page.s.dnd) }
                        HudToggle { width: parent.width; on: !!page.render.reducedMotion; caption: "Reduce motion"
                                    detail: "Stills the Nucleus, smoke and drifting effects. Everything still updates."
                                    onClicked: shell.setReducedMotion(!page.render.reducedMotion) }
                        HudToggle { width: parent.width; on: !!page.render.lockOnStart; caption: "Ask for my password when APVIS starts"
                                    detail: "Shows the lock screen after start-up. Lock any time with Win+L. The lock covers APVIS Home; close other windows before you step away."
                                    onClicked: shell.setLockOnStart(!page.render.lockOnStart) }
                        HudToggle { width: parent.width; on: !!shell.developerMode; caption: "Developer mode"
                                    detail: "Adds the DEV tab: logs, services and build details."
                                    onClicked: shell.setDeveloperMode(!shell.developerMode) }
                    }

                    HudPanel {
                        id: systemSec
                        width: parent.width; reveal: page.reveal; order: 7
                        title: "SYSTEM"; glyph: "device"
                        Row {
                            width: parent.width; spacing: 8
                            HudButton { width: (parent.width - 16) / 3; glyph: "wifi"; caption: "Network"; onClicked: shell.launch("network") }
                            HudButton { width: (parent.width - 16) / 3; glyph: "screen"; caption: "Displays"; onClicked: shell.launch("displays") }
                            HudButton { width: (parent.width - 16) / 3; glyph: "volume"; caption: "Sound"; onClicked: shell.launch("sound") }
                        }
                    }
                }

                // ================================ right lane
                Column {
                    width: lanes.laneWidth; spacing: 14

                    HudPanel {
                        id: aiSec
                        width: parent.width; reveal: page.reveal; order: 2
                        title: "ASK  ·  LOCAL AI"; glyph: "brain"
                        meta: page.s.ollamaUp === true ? "OLLAMA ONLINE" : page.s.ollamaUp === false ? "NOT RUNNING" : ""
                        metaColour: page.s.ollamaUp === true ? Theme.accent : Theme.attention
                        Note { text: "Where Ask finds Ollama: this computer (http://127.0.0.1:11434) or another computer on your home network, " +
                                     "e.g. your OptiPlex. Internet addresses are refused, so Ask stays local." }
                        Row {
                            width: parent.width; spacing: 8
                            TextField {
                                id: ollamaField
                                width: parent.width - 196; height: 38
                                // Not bound: a settings update must never overwrite what the owner typed.
                                Component.onCompleted: text = page.s.ollamaUrl || ""
                                Connections {
                                    target: shell
                                    function onSettingsChanged() {
                                        if ((page.s.saved || "").startsWith("Saved")) ollamaField.text = page.s.ollamaUrl
                                    }
                                }
                                color: Theme.text; selectByMouse: true; font.pixelSize: 13; font.family: Theme.monoFont; verticalAlignment: TextInput.AlignVCenter
                                leftPadding: 12
                                Accessible.name: "Ollama address"
                                background: Chamfer { cut: 8; fill: Theme.bgBottom; fillOpacity: 0.6
                                                      stroke: ollamaField.activeFocus ? Theme.accent : Theme.line; strokeWidth: ollamaField.activeFocus ? 1.5 : 1 }
                                onAccepted: shell.testOllama(text)
                            }
                            HudButton { width: 90; caption: "Test"; onClicked: shell.testOllama(ollamaField.text) }
                            HudButton { width: 90; caption: "Save"; tone: "primary"; onClicked: shell.saveOllama(ollamaField.text) }
                        }
                        Note {
                            visible: text.length > 0
                            text: page.s.saved || page.s.test || ""
                            color: (page.s.saved || "").startsWith("Saved") || page.s.testOk ? Theme.accent :
                                   (page.s.test === "Testing…" ? Theme.muted : Theme.attention)
                        }
                        Label { text: Theme.label("ANSWER LENGTH") }
                        Segmented {
                            options: ["short", "normal", "detailed"]
                            label: v => ({ short: "Short", normal: "Normal", detailed: "Detailed" })[v]
                            value: page.s.answerLength || "normal"
                            onPicked: v => shell.setAnswerLength(v)
                        }
                        Note { text: "Short answers finish sooner on this computer; Detailed gives fuller explanations. Follow-up questions remember the last few messages for 30 minutes, on this computer only." }
                        Label { text: Theme.label("MODELS") }
                        HudButton {
                            visible: page.s.ollamaUp === false
                            width: 230; glyph: "brain"; tone: "primary"; caption: "Set up local AI…"
                            onClicked: shell.setupLocalAI()
                        }
                        Note { visible: page.s.ollamaUp === false
                               text: "Ollama isn't running here. This installs it and the recommended models in a terminal window (you type your password there)." }
                        Repeater {
                            model: shell.recommendedModels || []
                            delegate: Item {
                                id: modelRow
                                required property var modelData
                                readonly property bool have: (page.s.installedModels || []).indexOf(modelData.name) >= 0
                                readonly property bool pulling: page.s.pulling === modelData.name
                                width: parent.width; height: 50
                                Chamfer { anchors.fill: parent; cut: 8; fill: Theme.bgBottom; fillOpacity: 0.5
                                          stroke: modelRow.have ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.45) : Theme.line }
                                Rectangle { x: 14; anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4
                                            color: modelRow.have ? Theme.accent : Theme.muted }
                                Column {
                                    x: 32; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 32 - 140
                                    Text { text: modelRow.modelData.name + "   " + modelRow.modelData.size; color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 12 }
                                    Text { width: parent.width; text: modelRow.modelData.role; color: Theme.muted; font.pixelSize: 11; elide: Text.ElideRight }
                                }
                                HudButton {
                                    anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                                    visible: page.s.ollamaUp === true && !modelRow.have
                                    enabled: !page.s.pulling
                                    width: 120; implicitHeight: 30; glyph: modelRow.pulling ? "" : "storage"
                                    caption: modelRow.pulling ? (page.s.pullPct || 0) + "%" : "Download"
                                    onClicked: shell.pullModel(modelRow.modelData.name)
                                }
                                Text { visible: modelRow.have; anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter
                                       text: "✓ INSTALLED"; color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 1.4 : 0.3 }
                                // Download progress along the bottom edge.
                                Rectangle { visible: modelRow.pulling; x: 8; anchors.bottom: parent.bottom; anchors.bottomMargin: 3; height: 2
                                            width: (parent.width - 16) * (page.s.pullPct || 0) / 100; color: Theme.accent
                                            Behavior on width { NumberAnimation { duration: 400 } } }
                            }
                        }
                        Note { visible: !!page.s.pullMessage; text: page.s.pullMessage || "" }

                        // Gaming PC boost: bigger models on the owner's GPU when that PC is on.
                        Label { text: Theme.label("GAMING PC BOOST") }
                        Note { text: "When your gaming PC is on and runs Ollama, Ask uses it and bigger models answer on its graphics card " +
                                     "(for example llama3.1:8b or qwen2.5-coder:7b). When it's off, this computer answers as usual and nothing waits for it. " +
                                     "On the gaming PC: install Ollama, set OLLAMA_HOST=0.0.0.0 so your network can reach it, and download a model." }
                        Row {
                            width: parent.width; spacing: 8
                            TextField {
                                id: boostField
                                width: parent.width - 196; height: 38
                                Component.onCompleted: text = (page.s.boost || {}).url || ""
                                Connections { target: shell; function onSettingsChanged() { if (!boostField.activeFocus && !boostField.text) boostField.text = (page.s.boost || {}).url || "" } }
                                placeholderText: "http://192.168.1.x:11434"; placeholderTextColor: Theme.muted
                                color: Theme.text; selectByMouse: true; font.pixelSize: 13; font.family: Theme.monoFont; verticalAlignment: TextInput.AlignVCenter
                                leftPadding: 12
                                Accessible.name: "Gaming PC Ollama address"
                                background: Chamfer { cut: 8; fill: Theme.bgBottom; fillOpacity: 0.6
                                                      stroke: boostField.activeFocus ? Theme.accent : Theme.line; strokeWidth: boostField.activeFocus ? 1.5 : 1 }
                                onAccepted: shell.setBoost(text, true)
                            }
                            HudButton { width: 90; caption: "Find"; glyph: "search"; onClicked: shell.findBoost() }
                            HudButton { width: 90; caption: "Save"; tone: "primary"; onClicked: shell.setBoost(boostField.text, true) }
                        }
                        Flow {
                            visible: (page.s.boostFound || []).length > 0
                            width: parent.width; spacing: 8
                            Repeater { model: page.s.boostFound || []
                                       delegate: HudButton { required property var modelData; width: 230; implicitHeight: 30; caption: modelData
                                                             onClicked: boostField.text = modelData } }
                        }
                        HudToggle {
                            width: parent.width
                            readonly property var b: page.s.boost || ({})
                            on: !!b.enabled
                            enabled: !!b.url || boostField.text.length > 0
                            caption: "Use the gaming PC when it's on"
                            detail: !b.enabled ? "Off: Ask always uses this computer." :
                                    b.reachable === true ? "ONLINE · everyday answers: " + (b.fast || "no suitable model yet") + (b.code ? " · code: " + b.code : "") :
                                    b.reachable === false ? "Off or unreachable right now, so this computer answers. Checked every 30 seconds." : "Checking…"
                            onClicked: shell.setBoost(boostField.text || (b.url || ""), !on)
                        }
                        Row {
                            width: parent.width; spacing: 8
                            TextField {
                                id: macField
                                width: parent.width - 196; height: 38
                                Component.onCompleted: text = (page.s.boost || {}).mac || ""
                                placeholderText: "Gaming PC network card (MAC) for Wake-on-LAN, optional"; placeholderTextColor: Theme.muted
                                color: Theme.text; selectByMouse: true; font.pixelSize: 13; font.family: Theme.monoFont; verticalAlignment: TextInput.AlignVCenter
                                leftPadding: 12
                                Accessible.name: "Gaming PC MAC address"
                                background: Chamfer { cut: 8; fill: Theme.bgBottom; fillOpacity: 0.6
                                                      stroke: macField.activeFocus ? Theme.accent : Theme.line; strokeWidth: macField.activeFocus ? 1.5 : 1 }
                                onAccepted: shell.setBoostMac(text)
                            }
                            HudButton { width: 90; caption: "Save"; onClicked: shell.setBoostMac(macField.text) }
                            HudButton { width: 90; caption: "Wake"; glyph: "power"; enabled: !!(page.s.boost || {}).mac; onClicked: shell.wakeBoost() }
                        }
                        Note { visible: !!page.s.boostMessage; text: page.s.boostMessage || "" }

                        // The APVIS API: the same brain for other apps on this computer.
                        Label { text: Theme.label("APVIS API") }
                        HudToggle {
                            width: parent.width
                            readonly property var a: page.s.api || ({})
                            on: a.enabled !== false
                            caption: "Local AI endpoint for your apps and scripts"
                            detail: (a.url || "http://127.0.0.1:8765") + (a.enabled === false ? " · off" : a.running === false ? " · another program is using the port" : " · running") +
                                    " · OpenAI-compatible /v1/chat/completions and /v1/ask. Only programs on this computer can use it."
                            onClicked: shell.setApiEnabled(!on)
                        }

                        // V3: search the vault by meaning (a local embedding model; notes never leave this computer).
                        Label { text: Theme.label("MEMORY SEARCH") }
                        HudToggle {
                            width: parent.width
                            readonly property var m: page.s.memory || ({})
                            on: !!m.enabled
                            caption: "Find notes by meaning, not just matching words"
                            detail: !m.enabled ? "Off: your vault is searched by words only." :
                                    m.state === "ready" ? "On · " + m.notes + " notes read with " + m.model + " on this computer" :
                                    m.state === "paused" ? "On · paused while you ask; carries on after" :
                                    m.state === "error" || m.state === "no-model" ? "On · waiting: " + (m.message || "local AI unavailable") :
                                    "On · reading your notes…"
                            onClicked: shell.setSemanticMemory(!on)
                        }
                        Note { visible: !!page.s.memoryMessage; text: page.s.memoryMessage || "" }

                        // V3 M4: one-line summaries of Ask sessions, kept 30 days (off until switched on).
                        Label { text: Theme.label("SESSION MEMORY") }
                        HudToggle {
                            width: parent.width
                            on: !!(page.s.episodes || {}).enabled
                            caption: "Remember what we talked about, for 30 days"
                            detail: on ? "On · each Ask session gets a one-line summary, written by the local model while the computer is idle. See or forget them in Memory."
                                       : "Off: sessions are not remembered."
                            onClicked: shell.setEpisodes(!on)
                        }
                        Note { visible: !!page.s.episodesMessage; text: page.s.episodesMessage || "" }

                        // V4: web search when Ask is unsure (owner's choice, 2026-10-19). On unless switched off.
                        Label { text: Theme.label("WEB SEARCH") }
                        HudToggle {
                            width: parent.width
                            on: (page.s.webSearch || {}).enabled !== false
                            caption: "Search the web when unsure"
                            detail: on ? "On · only the search words are sent (to DuckDuckGo or Wikipedia), never your notes, files or chats."
                                       : "Off: Ask answers from local models only."
                            onClicked: shell.setWebSearch(!on)
                        }
                    }

                    HudPanel {
                        id: backupSec
                        width: parent.width; reveal: page.reveal; order: 4
                        title: "BACKUP"; glyph: "storage"
                        readonly property var b: page.s.backup || ({})
                        property string confirm: ""
                        Component.onCompleted: shell.refreshBackups()
                        Note { text: "Saves your notes and memories, Home's settings, Ask's settings and history, reminders, missions, pinned apps " +
                                     "and browser history into one file. Back up to a USB drive before reinstalling, then restore here." }
                        Label { text: Theme.label("BACK UP TO") }
                        Repeater {
                            model: backupSec.b.targets || []
                            delegate: Item {
                                required property var modelData
                                width: parent.width; height: 46
                                Chamfer { anchors.fill: parent; cut: 8; fill: Theme.bgBottom; fillOpacity: 0.5; stroke: Theme.line }
                                Glyph { x: 12; anchors.verticalCenter: parent.verticalCenter; width: 18; height: 18
                                        kind: modelData.kind === "drive" ? "storage" : "files"; stroke: Theme.accent }
                                Column {
                                    x: 40; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 40 - 160
                                    Text { width: parent.width; elide: Text.ElideMiddle; text: modelData.label; color: Theme.text; font.pixelSize: 13 }
                                    Text { text: (modelData.free / 1073741824).toFixed(1) + " GB free"; color: Theme.muted; font.pixelSize: 11 }
                                }
                                HudButton { anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                                            width: 140; implicitHeight: 30; caption: "Back up here"; enabled: !page.s.backupBusy
                                            onClicked: shell.backupTo(modelData.path) }
                            }
                        }
                        Note { visible: (backupSec.b.targets || []).length <= 1; text: "Plug in a USB drive to back up to it." }
                        Label { visible: (backupSec.b.found || []).length > 0; text: Theme.label("BACKUPS FOUND") }
                        Repeater {
                            model: backupSec.b.found || []
                            delegate: Item {
                                required property var modelData
                                width: parent.width; height: 46
                                Chamfer { anchors.fill: parent; cut: 8; fill: Theme.bgBottom; fillOpacity: 0.5
                                          stroke: backupSec.confirm === modelData.path ? Theme.attention : Theme.line }
                                Column {
                                    x: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 12 - 170
                                    Text { width: parent.width; elide: Text.ElideMiddle; text: modelData.name; color: Theme.text; font.pixelSize: 12; font.family: Theme.monoFont }
                                    Text { text: Qt.formatDateTime(new Date(modelData.time * 1000), "d MMM yyyy HH:mm") + "  ·  " +
                                                 (modelData.size / 1048576).toFixed(1) + " MB  ·  " + modelData.where; color: Theme.muted; font.pixelSize: 11 }
                                }
                                HudButton { anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                                            width: 150; implicitHeight: 30; enabled: !page.s.backupBusy
                                            tone: backupSec.confirm === modelData.path ? "warning" : "normal"
                                            caption: backupSec.confirm === modelData.path ? "Press to restore" : "Restore…"
                                            onClicked: { if (backupSec.confirm === modelData.path) { backupSec.confirm = ""; shell.restoreBackup(modelData.path) }
                                                         else backupSec.confirm = modelData.path } }
                            }
                        }
                        Row {
                            spacing: 8
                            HudButton { width: 120; implicitHeight: 32; caption: "Refresh"; onClicked: shell.refreshBackups() }
                            HudButton { visible: !!page.s.backupRestored; width: 160; implicitHeight: 32; tone: "primary"; glyph: "restart"
                                        caption: "Restart Home"; onClicked: shell.restartHome() }
                        }
                        Note { visible: !!page.s.backupMessage; text: page.s.backupMessage || ""
                               color: (page.s.backupMessage || "").indexOf("didn't") >= 0 ? Theme.attention : Theme.accent }
                    }

                    HudPanel {
                        id: updatesSec
                        width: parent.width; reveal: page.reveal; order: 4
                        title: "UPDATES"; glyph: "restart"
                        tint: page.u.state === "available" ? Theme.attention : Theme.accent
                        highlighted: page.u.state === "available"
                        meta: page.u.state === "available" ? "UPDATE READY" : page.u.state === "current" ? "UP TO DATE" : ""
                        metaColour: page.u.state === "available" ? Theme.attention : Theme.accent
                        Row {
                            spacing: 12
                            Column {
                                spacing: 1
                                Label { text: Theme.label("INSTALLED") }
                                Text { text: page.u.installed || "?"; color: Theme.text; font.pixelSize: 18; font.family: Theme.monoFont }
                            }
                            Column {
                                visible: page.u.state === "available"
                                spacing: 1
                                Label { text: Theme.label("AVAILABLE") }
                                Text { text: "→ " + (page.u.latest || ""); color: Theme.attention; font.pixelSize: 18; font.family: Theme.monoFont }
                            }
                        }
                        Text { visible: !!page.u.fromUpdate; text: "Update on top of " + page.u.base; color: Theme.muted; font.pixelSize: 11 }
                        Row {
                            spacing: 8
                            HudButton {
                                width: 170; glyph: "search"; caption: page.u.state === "checking" ? "Checking…" : "Check for updates"
                                enabled: ["checking", "installing"].indexOf(page.u.state) < 0
                                onClicked: shell.checkUpdates()
                            }
                            HudButton {
                                id: installButton
                                property bool armed: false
                                visible: page.u.state === "available"
                                width: 200; glyph: "check"
                                tone: armed ? "warning" : "primary"
                                caption: armed ? "Press again to install" : "Install " + (page.u.latest || "")
                                Timer { id: installDisarm; interval: 4000; onTriggered: installButton.armed = false }
                                onClicked: { if (armed) { armed = false; shell.installUpdate() } else { armed = true; installDisarm.restart() } }
                            }
                            HudButton {
                                visible: !!page.u.fromUpdate && ["checking", "installing"].indexOf(page.u.state) < 0
                                width: 110; glyph: "restart"; caption: "Roll back"
                                onClicked: shell.rollbackUpdate()
                            }
                        }
                        Note {
                            visible: text.length > 0
                            text: page.u.message || ""
                            color: ["error"].indexOf(page.u.state) >= 0 ? Theme.attention :
                                   ["available", "installed", "current", "rolledback"].indexOf(page.u.state) >= 0 ? Theme.accent : Theme.muted
                        }
                        Note { visible: !!page.u.notes; color: Theme.text; text: "What's new: " + (page.u.notes || "") }
                        Repeater {
                            model: (page.u.history || []).slice(0, 3)
                            delegate: Text { required property var modelData
                                             width: parent.width; elide: Text.ElideRight
                                             text: modelData.at + "  " + modelData.event + " " + modelData.version + (modelData.detail ? " · " + modelData.detail : "")
                                             color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10 }
                        }
                        Note { text: "Updates change only APVIS itself (screens and features), are checked against APVIS's signature before " +
                                     "anything is replaced, and roll back automatically if Home fails to start." }
                    }

                    HudPanel {
                        id: aboutSec
                        width: parent.width; reveal: page.reveal; order: 6
                        title: "ABOUT"; glyph: "apvis"
                        HudButton {
                            visible: !!(shell.installer || {}).live
                            width: 220; glyph: "device"; tone: "primary"
                            caption: "Install APVIS OS…"
                            onClicked: shell.pageRequested("install")
                        }
                        Column {
                            width: parent.width
                            Kv { k: "VERSION"; v: page.s.version || "" }
                            Kv { k: "GRAPHICS"; v: page.render.software ? "CPU (software renderer)" :
                                                   page.render.renderer === "canvas" ? "GPU · 2D Nucleus" : "GPU · 3D Nucleus" }
                            Kv { k: "QUALITY"; v: page.render.tier || "" }
                            Kv { k: "ACCENT"; v: page.render.accent || "" }
                            Kv { visible: (shell.frameInfo || {}).fps !== undefined
                                 k: "FRAME RATE"; v: (shell.frameInfo || {}).fps + " fps  ·  slowest 5%: " + (shell.frameInfo || {}).p95 + " ms" }
                            Kv { k: "HOST"; v: page.sys.hostname || "" }
                        }
                    }
                }
            }
        }
    }
}
