import QtQuick
import QtQuick.Controls
import "../theme"

// 09 APPS STORE (owner concept): open what is installed, get more from Debian or
// Flathub, and open APVIS's own apps. Real data only: installed apps are this
// computer's desktop entries, catalog apps say whether they are really installed,
// and installs run through the APVIS helper after the owner's password.
Item {
    id: page
    signal act(string key)
    readonly property var st: shell.apps || ({})
    readonly property var job: st.job || ({})
    readonly property var can: st.canInstall || ({})
    readonly property var s: shell.settings || ({})
    property string category: "featured"
    property string tab: "all"
    property var detail: null
    property string pending: ""                  // "install" | "remove" while the password row shows
    onVisibleChanged: if (visible) { shell.refreshApps(); shell.refreshModels(); entry.restart(); Qt.callLater(focusFirst) }
    Component.onCompleted: if (visible) { shell.refreshApps(); shell.refreshModels() }
    // Preview hooks: "apps:<category>" shows that category, "apps:app=<id>" opens its details.
    Timer {
        running: typeof previewPage === "string" && previewPage.startsWith("apps:"); interval: 900
        onTriggered: {
            const arg = previewPage.slice(5)
            if (arg.startsWith("app=")) page.showDetail(page.all.find(i => i.id === arg.slice(4)) || null)
            else if (arg.startsWith("find=")) search.text = arg.slice(5)
            else page.category = arg
        }
    }
    // Brand colours for the icon tile of an app that isn't installed yet (its real icon comes with it).
    readonly property var tints: Theme.brandTints
    function focusFirst() { search.forceActiveFocus() }
    property real reveal: 1
    NumberAnimation { id: entry; target: page; property: "reveal"; from: 0; to: 1; duration: 700; easing.type: Easing.OutCubic }

    readonly property var categories: [["featured", "Featured", "core"], ["productivity", "Productivity", "notes"],
        ["development", "Development", "terminal"], ["creativity", "Creativity", "screen"], ["media", "Media", "volume"],
        ["internet", "Internet", "wifi"], ["utilities", "Utilities", "settings"], ["apvis", "APVIS Apps", "apvis"],
        ["selfhosted", "Self-Hosted", "storage"], ["installed", "Installed", "check"]]

    // ---- one list of everything the store shows
    readonly property var installedById: {
        const out = {}
        for (const a of (st.installed || [])) out[a.id] = a
        return out
    }
    readonly property var all: {
        const inst = installedById, covered = {}
        const cat = (st.catalog || []).map(a => {
            if (a.installed && a.desktop) covered[a.desktop] = true
            return { key: "c:" + a.id, kind: "catalog", id: a.id, name: a.name, summary: a.summary, category: a.category,
                     installed: a.installed, openable: a.openable, desktop: a.desktop, source: a.source, ref: a.ref,
                     about: a.about, featured: a.featured, type: a.kind === "service" ? "services" : "applications",
                     icon: inst[a.desktop] ? inst[a.desktop].icon : "" }
        })
        const builtin = (st.builtin || []).map(b => ({ key: "b:" + b.id, kind: "builtin", id: b.id, name: b.name, summary: b.summary,
                                                      glyph: b.glyph, action: b.action, category: "apvis", installed: true, type: "applications" }))
        const local = (st.installed || []).filter(a => !covered[a.id]).map(a => ({ key: "i:" + a.id, kind: "installed", id: a.id, name: a.name,
                                                      summary: a.summary, icon: a.icon, category: a.category, installed: true, type: "applications" }))
        const have = s.installedModels || []
        const models = (shell.recommendedModels || []).map(m => ({ key: "m:" + m.name, kind: "model", id: m.name, name: m.name,
                                                      summary: m.role, size: m.size, glyph: "brain", category: "extensions",
                                                      installed: have.indexOf(m.name) >= 0, type: "extensions" }))
        return builtin.concat(cat, local, models)
    }
    readonly property string query: search.text.trim().toLowerCase()
    function matches(it) {
        if (tab !== "all" && it.type !== tab) return false
        if (query.length) return (it.name + " " + (it.summary || "") + " " + (it.ref || "")).toLowerCase().indexOf(query) >= 0
        if (tab !== "all") return category === "featured" || category === "installed" ? (category !== "installed" || it.installed) : it.category === category
        if (category === "installed") return it.installed && it.kind !== "model" && it.kind !== "builtin"
        if (category === "apvis") return it.kind === "builtin"
        return it.category === category && it.kind !== "builtin"
    }
    readonly property bool featuredView: category === "featured" && !query.length && tab === "all"
    readonly property var filtered: featuredView ? [] : all.filter(matches)
    readonly property var featured: all.filter(i => i.featured)
    readonly property var apvisApps: all.filter(i => i.kind === "builtin")
    readonly property var onComputer: all.filter(i => i.installed && (i.kind === "installed" || i.kind === "catalog"))
    readonly property var live: detail ? (all.find(i => i.key === detail.key) || detail) : null
    readonly property var prefs: st.prefs || ({ recent: [], pinned: [] })
    readonly property var recent: (prefs.recent || []).map(k => all.find(i => i.key === k)).filter(i => !!i && i.installed)
    function pinned(it) { return !!it && (prefs.pinned || []).indexOf(it.key) >= 0 }

    function open(it) {
        const launches = it.kind === "builtin" || it.kind === "installed" || (it.kind === "catalog" && it.openable)
        if (launches) shell.noteApp(it.key)
        if (it.kind === "builtin") page.act(it.action)
        else if (it.kind === "installed") shell.launchApp(it.id)
        else if (it.kind === "catalog" && it.openable) shell.launchApp(it.desktop)
        else { page.pending = ""; page.detail = it }
    }
    function showDetail(it) { page.pending = ""; pw.text = ""; page.detail = it }
    // "install VLC" in Ask opens the store at that app (the password is asked here).
    property int focusSeen: 0
    function checkFocus() {
        const f = st.focus
        if (!f || f.n === focusSeen) return
        const it = all.find(i => i.kind === "catalog" && i.id === f.id)
        if (it) { focusSeen = f.n; showDetail(it) }
    }
    onAllChanged: checkFocus()
    function firstResult() { const list = featuredView ? all.filter(i => i.installed) : filtered; return list.length ? list[0] : null }

    PageHeader {
        id: header
        width: parent.width; reveal: page.reveal
        code: "09"; title: "APPS STORE"
        subtitle: "Linux apps, APVIS apps, more."
    }

    // ------------------------------------------------------------ the store panel
    Item {
        id: panel
        anchors.fill: parent; anchors.topMargin: header.height + 10
        opacity: page.reveal
        Chamfer { anchors.fill: parent; cut: 14; fill: Theme.panel; fillOpacity: 0.72; fill2: Theme.bgBottom; fill2Opacity: 0.8
                  stroke: Theme.line; edgeGlow: true }

        // Categories
        Column {
            id: side
            x: 14; y: 16; width: 200; spacing: 3
            Repeater {
                model: page.categories
                delegate: AbstractButton {
                    id: catBtn
                    required property var modelData
                    required property int index
                    readonly property bool sel: page.category === modelData[0] && page.tab !== "extensions"
                    width: side.width; height: 38
                    topPadding: index === page.categories.length - 1 ? 14 : 0
                    onClicked: { page.category = modelData[0]; if (page.tab === "extensions") page.tab = "all"; search.text = "" }
                    Accessible.name: modelData[1]
                    background: Item {
                        Rectangle { anchors.fill: parent; anchors.topMargin: catBtn.topPadding; radius: 8
                                    color: catBtn.sel ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12) : catBtn.hovered ? Theme.sheen(0.04) : "transparent"
                                    border.width: catBtn.sel ? 1 : 0; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.5) }
                    }
                    contentItem: Row {
                        leftPadding: 12; spacing: 12
                        Glyph { width: 18; height: 18; anchors.verticalCenter: parent.verticalCenter; kind: catBtn.modelData[2]
                                stroke: catBtn.sel ? Theme.accent : Theme.muted }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: catBtn.modelData[1]; font.pixelSize: 13
                               color: catBtn.sel ? Theme.text : Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, 0.75) }
                    }
                }
            }
        }
        Rectangle { x: side.x + side.width + 12; y: 14; width: 1; height: parent.height - 28; color: Theme.line; opacity: 0.7 }

        // Tabs + search
        Item {
            id: bar
            x: side.x + side.width + 28; y: 14; width: parent.width - x - 16; height: 40
            Segmented {
                id: tabs
                anchors.verticalCenter: parent.verticalCenter
                options: ["all", "applications", "services", "extensions"]
                label: v => ({ all: "All", applications: "Applications", services: "Services", extensions: "AI Models" })[v]
                value: page.tab
                onPicked: v => page.tab = v
            }
            TextField {
                id: search
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                width: Math.min(300, parent.width - tabs.width - 20); height: 36
                placeholderText: "Search apps…"; leftPadding: 34
                color: Theme.text; placeholderTextColor: Theme.muted; font.pixelSize: 13; verticalAlignment: TextInput.AlignVCenter
                Accessible.name: "Search apps"
                background: Rectangle { radius: 8; color: Theme.sheen(0.04); border.width: search.activeFocus ? 1.5 : 1
                                        border.color: search.activeFocus ? Theme.accent : Theme.line
                                        Glyph { x: 10; anchors.verticalCenter: parent.verticalCenter; width: 16; height: 16; kind: "search"; stroke: Theme.muted } }
                onAccepted: { const it = page.firstResult(); if (it) page.open(it) }
                Keys.onDownPressed: flick.forceActiveFocus()
            }
        }

        Flickable {
            id: flick
            x: bar.x; y: bar.y + bar.height + 14; width: bar.width; height: parent.height - y - 34
            contentHeight: content.height + 16; clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: HudScrollBar {}
            readonly property int cols: Math.max(2, Math.floor((width + 14) / 200))
            readonly property real cellW: (width - 14 * (cols - 1) - 8) / cols
            Column {
                id: content
                width: flick.width - 8; spacing: 12

                // Featured view: Recently used, Featured, APVIS Apps, On this computer
                Section { visible: page.featuredView && page.recent.length > 0; title: "Recently used"; items: page.recent.slice(0, flick.cols) }
                Section { visible: page.featuredView; title: "Featured"; items: page.featured }
                Section { visible: page.featuredView; title: "APVIS Apps"; items: page.apvisApps.slice(0, flick.cols); more: "apvis"
                          count: page.apvisApps.length }
                Section { visible: page.featuredView; title: "On this computer"; items: page.onComputer.slice(0, flick.cols * 2); more: "installed"
                          count: page.onComputer.length; empty: "Apps on this computer show up here." }
                // Any other view: one grid
                Section { visible: !page.featuredView; items: page.filtered
                          title: page.query.length ? "Results for “" + search.text.trim() + "”" :
                                 page.tab === "extensions" ? "AI Models for Ask" :
                                 (page.categories.find(c => c[0] === page.category) || ["", ""])[1] + (page.tab === "services" ? " · Services" : "")
                          empty: page.query.length ? "Nothing matches. Try another word." :
                                 page.category === "installed" ? "Nothing installed yet." : "Nothing here yet." }
            }
        }
        Text {
            anchors.left: bar.left; anchors.right: parent.right; anchors.rightMargin: 16; anchors.bottom: parent.bottom; anchors.bottomMargin: 10
            elide: Text.ElideRight; font.pixelSize: 11
            color: page.job.state === "error" ? Theme.attention : Theme.muted
            text: page.job.state === "checking" || page.job.state === "running" ? page.job.message || "" :
                  page.st.message ? page.st.message : shell.guest ? "Guest can open the apps on this computer. Installing needs the APVIS account."
                                                    : (page.can.debian ? "Apps come from Debian, and from Flathub where Debian has no build. Installing asks for your password."
                                                      : "Opening apps works here. Installing new apps needs APVIS OS installed on a computer.")
        }
    }

    // A titled grid of app cards.
    component Section: Column {
        id: sec
        property string title: ""
        property var items: []
        property string more: ""
        property int count: items.length
        property string empty: ""
        width: parent ? parent.width : 400; spacing: 10
        Item {
            width: parent.width; height: 26
            Text { anchors.verticalCenter: parent.verticalCenter; text: sec.title; color: Theme.text; font.pixelSize: 19; font.weight: Font.DemiBold }
            Text { visible: sec.more.length > 0; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                   text: "View all" + (sec.count > sec.items.length ? " (" + sec.count + ")" : ""); color: Theme.accent; font.pixelSize: 12
                   MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: page.category = sec.more } }
        }
        Flow {
            width: parent.width; spacing: 14
            Repeater { model: sec.items; delegate: AppCard {} }
        }
        Text { visible: sec.items.length === 0 && sec.empty.length > 0; text: sec.empty; color: Theme.muted; font.pixelSize: 13; topPadding: 20 }
        Item { width: 1; height: 6 }
    }

    // The app's icon: its real icon, an APVIS glyph, or a monogram when there is none yet.
    component AppIcon: Item {
        id: ic
        property var item: ({})
        readonly property bool real: img.status === Image.Ready && img.implicitWidth > 1
        Image {
            id: img
            anchors.fill: parent
            visible: ic.real
            source: ic.item.icon ? "image://appicon/" + encodeURIComponent(ic.item.icon) : ""
            sourceSize: Qt.size(96, 96); smooth: true; asynchronous: true; fillMode: Image.PreserveAspectFit
        }
        Rectangle {
            id: tile
            readonly property color tint: page.tints[ic.item.id] || Theme.accent
            visible: !ic.real
            anchors.fill: parent; radius: width * 0.26
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.rgba(tile.tint.r, tile.tint.g, tile.tint.b, ic.item.kind === "builtin" ? 0.14 : 0.22) }
                GradientStop { position: 1; color: Qt.rgba(tile.tint.r, tile.tint.g, tile.tint.b, 0.04) }
            }
            border.width: 1; border.color: Qt.rgba(tint.r, tint.g, tint.b, 0.45)
            Glyph { visible: !!ic.item.glyph; anchors.centerIn: parent; width: parent.width * 0.5; height: width; kind: ic.item.glyph || "apps"; stroke: parent.tint }
            Text { visible: !ic.item.glyph; anchors.centerIn: parent; text: (ic.item.name || "?").charAt(0).toUpperCase()
                   color: parent.tint; font.pixelSize: parent.width * 0.46; font.weight: Font.DemiBold }
        }
    }

    component AppCard: AbstractButton {
        id: card
        required property var modelData
        readonly property var it: modelData
        readonly property bool busy: page.job.id === it.id && (page.job.state === "running" || page.job.state === "checking")
        width: flick.cellW; height: 164
        hoverEnabled: true
        onClicked: page.open(it)
        Accessible.name: it.name + ", " + (it.summary || "")
        background: Chamfer { cut: 10; fill: card.hovered ? Theme.raised : Theme.bgBottom; fillOpacity: card.hovered ? 0.9 : 0.55
                              stroke: card.hovered || card.activeFocus ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7) : Theme.line
                              edgeGlow: card.hovered }
        contentItem: Item {
            AppIcon { item: card.it; width: 52; height: 52; anchors.horizontalCenter: parent.horizontalCenter; y: 20 }
            Column {
                y: 84; width: parent.width - 16; anchors.horizontalCenter: parent.horizontalCenter; spacing: 3
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight; text: card.it.name
                       color: Theme.text; font.pixelSize: 14; font.weight: Font.DemiBold }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                       text: card.it.kind === "model" ? card.it.size : (card.it.summary || " "); color: Theme.muted; font.pixelSize: 11 }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; topPadding: 6; font.pixelSize: 10; font.letterSpacing: 1.3
                       font.family: Theme.monoFont
                       color: card.it.installed ? Theme.accent : Theme.muted
                       text: card.busy ? (page.job.pct >= 0 ? page.job.pct + "%" : "WORKING…") :
                             card.it.kind === "builtin" ? "BUILT IN" : card.it.installed ? (card.it.kind === "model" ? "✓ INSTALLED" : "OPEN") :
                             card.it.kind === "model" ? "DOWNLOAD" : (card.it.source === "flathub" ? "GET · FLATHUB" : "GET") }
            }
            // Details (pin to Home, remove, source).
            AbstractButton {
                visible: card.it.kind !== "model" && card.hovered
                anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 6
                width: 26; height: 26
                onClicked: page.showDetail(card.it)
                Accessible.name: "Details for " + card.it.name
                background: Rectangle { radius: 13; color: Theme.sheen(parent.hovered ? 0.1 : 0.05) }
                contentItem: Glyph { kind: "more"; stroke: Theme.muted }
            }
            Glyph { visible: page.pinned(card.it) && !card.hovered; anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 9
                    width: 14; height: 14; kind: "check"; stroke: Theme.accent; opacity: 0.8 }
            Rectangle { visible: card.busy && page.job.pct >= 0; anchors.bottom: parent.bottom; anchors.bottomMargin: 5; x: 10; height: 2; radius: 1
                        width: (parent.width - 20) * Math.max(0, page.job.pct) / 100; color: Theme.accent
                        Behavior on width { NumberAnimation { duration: 300 } } }
        }
        Keys.onReturnPressed: page.open(it)
    }

    // ------------------------------------------------------------ app details
    Rectangle {
        anchors.fill: parent
        visible: page.detail !== null
        color: Theme.shade(0.55)
        MouseArea { anchors.fill: parent; onClicked: page.detail = null }
        Keys.onEscapePressed: page.detail = null
        Item {
            id: sheet
            anchors.centerIn: parent
            width: Math.min(600, parent.width - 40); height: sheetCol.height + 44
            MouseArea { anchors.fill: parent }           // clicks inside keep it open
            Chamfer { anchors.fill: parent; cut: 14; fill: Theme.panel; fillOpacity: 0.97; fill2: Theme.bgBottom; fill2Opacity: 0.95
                      stroke: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.5); edgeGlow: true; brackets: true }
            readonly property var it: page.live || ({})
            readonly property bool mine: page.job.id === it.id
            readonly property bool busy: mine && (page.job.state === "running" || page.job.state === "checking")
            // Guest (V4) opens what is installed but never installs, removes or downloads.
            readonly property bool canGet: !shell.guest && (it.kind === "model" ? s.ollamaUp === true : !!page.can[it.source])
            Column {
                id: sheetCol
                x: 22; y: 22; width: parent.width - 44; spacing: 14
                Row {
                    spacing: 16
                    AppIcon { item: sheet.it; width: 64; height: 64 }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter; spacing: 4
                        Text { text: sheet.it.name || ""; color: Theme.text; font.pixelSize: 22; font.weight: Font.DemiBold }
                        Text { text: (sheet.it.summary || "") + (sheet.it.size ? "  ·  " + sheet.it.size : ""); color: Theme.muted; font.pixelSize: 13 }
                        Text { font.pixelSize: 11; font.family: Theme.monoFont; color: sheet.it.installed ? Theme.accent : Theme.muted
                               text: sheet.it.kind === "builtin" ? Theme.label("BUILT INTO APVIS") : sheet.it.kind === "installed" ? "✓ INSTALLED ON THIS COMPUTER" :
                                     (sheet.it.installed ? "✓ INSTALLED  ·  " : "") +
                                     (sheet.it.kind === "model" ? "OLLAMA MODEL" : sheet.it.source === "flathub" ? "FLATHUB  ·  " + sheet.it.ref : "DEBIAN  ·  " + (sheet.it.ref || "")) }
                    }
                }
                Text { visible: !!sheet.it.about; width: parent.width; wrapMode: Text.WordWrap; text: sheet.it.about || ""; color: Theme.text; font.pixelSize: 13 }
                Text {
                    visible: !sheet.canGet && !sheet.it.installed && sheet.it.kind !== "builtin" && sheet.it.kind !== "installed"
                    width: parent.width; wrapMode: Text.WordWrap; color: Theme.attention; font.pixelSize: 12
                    text: shell.guest ? "Guest can open installed apps. Installing needs the APVIS account." :
                          sheet.it.kind === "model" ? "Ollama isn't running on this computer." :
                          sheet.it.source === "flathub" && page.can.debian ? "Flathub apps need Flatpak, which this APVIS OS image does not have yet." :
                          "Installing apps needs APVIS OS installed on a computer. Everything already installed opens from here."
                }
                // Password (installs and removals change the system).
                Row {
                    visible: page.pending.length > 0 && !sheet.busy
                    spacing: 8
                    TextField {
                        id: pw
                        width: 240; height: 38; echoMode: TextInput.Password; verticalAlignment: TextInput.AlignVCenter
                        placeholderText: "Your password"; color: Theme.text; placeholderTextColor: Theme.muted; font.pixelSize: 13
                        Accessible.name: "Password"
                        background: Rectangle { radius: 6; color: Theme.raised; border.width: pw.activeFocus ? 2 : 1; border.color: pw.activeFocus ? Theme.accent : Theme.line }
                        onAccepted: confirm.clicked()
                    }
                    HudButton {
                        id: confirm
                        width: 170; tone: page.pending === "remove" ? "warning" : "primary"; enabled: pw.text.length > 0
                        caption: page.pending === "remove" ? "Remove " + (sheet.it.name || "") : "Install"
                        onClicked: { shell.appJob(page.pending, sheet.it.id, pw.text); pw.text = ""; page.pending = "" }
                    }
                }
                // Progress / result.
                Column {
                    visible: sheet.mine && !!page.job.state
                    width: parent.width; spacing: 6
                    Item {
                        visible: sheet.busy
                        width: parent.width; height: 6
                        Rectangle { anchors.fill: parent; radius: 3; color: Theme.sheen(0.07) }
                        Rectangle { visible: page.job.pct >= 0; height: parent.height; radius: 3; color: Theme.accent
                                    width: parent.width * Math.max(0, page.job.pct) / 100
                                    Behavior on width { NumberAnimation { duration: 300 } } }
                        Rectangle { visible: page.job.pct < 0; height: parent.height; radius: 3; width: parent.width * 0.25; color: Theme.accent
                                    SequentialAnimation on x { running: sheet.busy && page.job.pct < 0; loops: Animation.Infinite
                                        NumberAnimation { from: 0; to: sheet.width * 0.6; duration: 1000; easing.type: Easing.InOutSine }
                                        NumberAnimation { to: 0; duration: 1000; easing.type: Easing.InOutSine } } }
                    }
                    Text { width: parent.width; wrapMode: Text.WordWrap; text: page.job.message || ""; font.pixelSize: 12
                           color: page.job.state === "error" ? Theme.attention : page.job.state === "done" ? Theme.accent : Theme.text }
                }
                Text { visible: sheet.it.kind === "model" && s.pulling === sheet.it.id; text: s.pullMessage || ""; color: Theme.text; font.pixelSize: 12 }
                Row {
                    spacing: 10
                    HudButton { visible: (sheet.it.kind === "catalog" && !!sheet.it.openable) || sheet.it.kind === "installed" || sheet.it.kind === "builtin"
                                width: 130; tone: "primary"; glyph: "apps"; caption: "Open"
                                onClicked: { const it = sheet.it; page.detail = null; page.open(it) } }
                    HudButton { visible: (sheet.it.kind === "catalog" && !!sheet.it.openable) || sheet.it.kind === "installed" || sheet.it.kind === "builtin"
                                width: 150; glyph: page.pinned(sheet.it) ? "check" : "plus"
                                caption: page.pinned(sheet.it) ? "Pinned to Home" : "Pin to Home"
                                tone: page.pinned(sheet.it) ? "selected" : "normal"
                                onClicked: shell.togglePin(sheet.it.key) }
                    HudButton { visible: !sheet.it.installed && sheet.canGet && !sheet.busy && page.pending === "" && !(sheet.it.kind === "model" && s.pulling)
                                width: 150; tone: "primary"; glyph: "plus"; caption: sheet.it.kind === "model" ? "Download" : "Install"
                                onClicked: { if (sheet.it.kind === "model") shell.pullModel(sheet.it.id); else { page.pending = "install"; Qt.callLater(() => pw.forceActiveFocus()) } } }
                    HudButton { visible: sheet.it.kind === "catalog" && sheet.it.installed && sheet.canGet && !sheet.busy && page.pending === ""
                                width: 130; tone: "warning"; caption: "Remove"
                                onClicked: { page.pending = "remove"; Qt.callLater(() => pw.forceActiveFocus()) } }
                    HudButton { width: 110; caption: "Close"; onClicked: page.detail = null }
                }
            }
        }
    }
}
