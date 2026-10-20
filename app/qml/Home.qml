import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "theme"
import "controls"
import "pages"
import "nucleus"
import "atlas"
import "home"

// V2 Home in the owner's concept (2026-09-26): menu bar, brand block, left
// navigation, the core (a dark planet in green smoke), glass cards with real
// state, action tiles, and the Ask bar. Every number is measured or sourced.
Window {
    id: root
    visible: true
    visibility: previewWindowed ? Window.Windowed : (typeof desktopApp !== "undefined" && desktopApp) ? Window.FullScreen : Window.Maximized
    // Home is the desktop surface, not a decorated app window.
    flags: previewWindowed && previewSize.width === 0 ? Qt.Window : (Qt.Window | Qt.FramelessWindowHint)
    minimumWidth: 900
    minimumHeight: 620
    width: previewSize.width > 0 ? previewSize.width : 1440
    height: previewSize.height > 0 ? previewSize.height : 900
    color: Theme.ink
    title: "APVIS"

    // APVIS for Windows: an app layout (live feed, local AI, game) instead of the OS desktop pieces.
    readonly property bool app: typeof windowsApp !== "undefined" && windowsApp
    readonly property color pale: Theme.text
    readonly property color muted: Theme.muted
    Binding { target: Theme; property: "accentName"; value: (shell.render || {}).accent || "apvis" }
    Binding { target: Theme; property: "artDir"; value: (shell.render || {}).artDir || "" }
    Binding { target: Theme; property: "style"; value: (shell.render || {}).style || "glass" }
    Component.onCompleted: {
        shell.refreshApps()          // pinned apps dock + Apps Store
        shell.setSharedDisplay(sharedDisplay)
        shell.setFrameMeasuring(measuring)
        shell.setHomeIntel(!pageOpen)
        if (controlOpen) shell.refreshControl()
        if (!shell.guest && (previewPage === "lock" || (previewPage === "" && (shell.render || {}).lockOnStart))) lockScreen.engage()
    }
    readonly property bool locked: lockScreen.locked
    onLockedChanged: shell.setLockChrome(locked)
    // Guest (V4) has no password, so no lock screen: it logs out instead.
    function lockNow() { if (shell.guest) return; lockScreen.engage(); root.raise(); root.requestActivate() }
    Shortcut { sequences: ["Meta+L", "Ctrl+Alt+L"]; enabled: !root.locked; onActivated: root.lockNow() }
    readonly property var state: shell.state || ({})
    readonly property var focus: state.focus || null
    readonly property var counts: state.task_counts || ({})
    readonly property var sys: shell.system || ({})
    readonly property var route: shell.route || ({})
    property bool settingsOpen: previewPage === "settings" || previewPage.startsWith("settings:")
    // Smoke-test hook: "pins:<key>,<key>" pins those Apps Store items (use with a throwaway HOME).
    Timer { running: previewPage.startsWith("pins:"); interval: 1200
            onTriggered: previewPage.slice(5).split(",").forEach(k => shell.togglePin(k)) }
    // Smoke-test hook: "settings:<section>" opens Settings at that section.
    Timer { running: previewPage.startsWith("settings:"); interval: 900; onTriggered: settingsPage.jump(previewPage.slice(9)) }
    property bool missionsOpen: previewPage === "missions"
    property bool devOpen: previewPage === "dev"
    property bool systemOpen: previewPage === "system"
    property bool devicesOpen: previewPage === "devices"
    property bool gameOpen: previewPage.startsWith("game")
    // Game mode (APVIS for Windows): live game data, or a fixture for renders ("game-live").
    readonly property var game: previewPage === "game-live" || previewPage === "home-game"
        ? ({ available: true, active: true, name: "Cyberpunk 2077", exe: "Cyberpunk2077.exe", since_ms: Date.now() - 4380000,
             cpu: 46, ram: 61, procCpu: 31, procRamMb: 9420, fps: null,
             gpu: { name: "NVIDIA GeForce GTX 1080 Ti", util: 97, temp: 74, vramUsed: 8920, vramTotal: 11264, power: 241, clock: 1885, fan: 58 },
             history: { cpu: [38, 41, 44, 47, 45, 43, 46, 49, 46, 44, 45, 47, 46],
                        gpu: [91, 94, 96, 97, 98, 97, 95, 97, 98, 97, 96, 97, 97],
                        gpuTemp: [66, 68, 69, 70, 71, 72, 72, 73, 73, 74, 74, 74, 74] },
             today: [{ name: "Cyberpunk 2077", seconds: 4380 }, { name: "Rocket League", seconds: 2700 }],
             recent: [{ name: "Cyberpunk 2077", lastPlayedMs: Date.now(), totalSeconds: 151200 },
                      { name: "Rocket League", lastPlayedMs: Date.now() - 7200000, totalSeconds: 98400 },
                      { name: "Elden Ring", lastPlayedMs: Date.now() - 259200000, totalSeconds: 412000 }] })
        : (typeof shell.game !== "undefined" && shell.game) ? shell.game : ({})
    property bool appsOpen: previewPage === "apps" || previewPage.startsWith("apps:")
    // Booted with "Install APVIS OS" from the USB menu: open the installer.
    property bool installOpen: previewPage === "install" || !!(shell.installer || {}).requested
    property bool atlasOpen: previewPage === "atlas" || previewPage === "atlas-home"
    property bool notesOpen: previewPage === "notes" || previewPage.startsWith("notes:")
    Timer { running: previewPage.startsWith("notes:"); interval: 900; onTriggered: memoryPage.kindFilter = previewPage.slice(6) }
    // Smoke-test hook: visit Atlas, then return Home (renders the live card).
    Timer { running: previewPage === "atlas-home"; interval: 12000; onTriggered: root.openPage("") }
    // Smoke-test hooks: the goodbye screen (never runs the power action) and an open menu.
    Timer { running: previewPage === "goodbye"; interval: 300; onTriggered: { goodbye.action = "poweroff"; goodbye.t = 0.6 } }
    Timer { running: previewPage === "menu"; interval: 300; onTriggered: topBar.openMenu = "System" }
    Timer { running: previewPage === "windows"; interval: 300; onTriggered: topBar.openMenu = "Windows" }
    // Smoke-test hook: "search:<text>" opens search with that text.
    Timer { running: previewPage.startsWith("search:"); interval: 600; onTriggered: { root.openSearch(); searchField.text = previewPage.slice(7) } }
    readonly property bool pageOpen: settingsOpen || missionsOpen || atlasOpen || notesOpen || devOpen || installOpen || systemOpen || devicesOpen || appsOpen || gameOpen
    onPageOpenChanged: shell.setHomeIntel(!pageOpen)
    readonly property string currentPage: settingsOpen ? "settings" : missionsOpen ? "missions" : atlasOpen ? "atlas" : notesOpen ? "notes" :
                                          devOpen ? "dev" : installOpen ? "install" : systemOpen ? "system" : devicesOpen ? "devices" : gameOpen ? "game" :
                                          appsOpen ? "apps" : ""
    // Lite look (no GPU / minimal tier): decorative motion stops; the core and real data still live.
    readonly property bool lite: !!(shell.render || {}).lite
    readonly property bool calm: !!(shell.render || {}).reducedMotion || lite
    // Frame times only count while Home animates continuously (see setFrameMeasuring). Lite still counts:
    // the core keeps turning there, and without measurements the quality loop could never step back up
    // (the OptiPlex sat at "minimal" for good after one busy start, 3.0.8). Software rendering stays lite anyway.
    readonly property bool measuring: !pageOpen && !(shell.render || {}).reducedMotion && nucleus.animating
    onMeasuringChanged: shell.setFrameMeasuring(measuring)
    property date nowTick: new Date()
    Timer { interval: 1000; running: true; repeat: true; onTriggered: root.nowTick = new Date() }
    // Last time someone used Home (pointer moves, typing in Ask). After two quiet minutes the core turns slower.
    property real lastInput: Date.now()
    readonly property bool userIdle: nowTick.getTime() - lastInput > 120000
    HoverHandler { onPointChanged: root.lastInput = Date.now() }
    Connections {
        target: shell
        function onPageRequested(name) { root.openPage(name) }
        function onReminderDue(text, kind) { reminderToast.add(text, kind) }
        function onDevChanged() { if (!shell.developerMode && root.devOpen) root.devOpen = false }
        function onPowerRequested(action) { root.powerMenuOpen = false; root.controlOpen = false; goodbye.start(action) }
    }
    // Opening a page puts the keyboard in its first field (Esc returns to Ask).
    onNotesOpenChanged: if (notesOpen) Qt.callLater(() => memoryPage.focusFirst())
    onSettingsOpenChanged: if (settingsOpen) Qt.callLater(() => settingsPage.focusFirst())
    onAppsOpenChanged: if (appsOpen) Qt.callLater(() => appsPage.focusFirst())
    function openPage(name) {
        settingsOpen = name === "settings"; missionsOpen = name === "missions"; atlasOpen = name === "atlas"
        notesOpen = name === "notes"; devOpen = name === "dev" && shell.developerMode
        systemOpen = name === "system"; devicesOpen = name === "devices"; appsOpen = name === "apps"; gameOpen = name === "game"
        installOpen = name === "install" && !!(shell.installer || {}).live
        if (name === "") Qt.callLater(() => focusInput.forceActiveFocus())
    }
    // Example chips on the pages put their text in the Ask bar (the owner still presses Enter).
    function suggestAsk(text) { openPage(""); focusInput.text = text; focusInput.forceActiveFocus(); focusInput.cursorPosition = text.length }
    // Menu bar, navigation, tiles and cards all speak in one set of action keys.
    function act(key) {
        if (key.startsWith("page:")) openPage(key.slice(5))
        else if (key === "launch:apps") openPage("apps")
        else if (key.startsWith("launch:")) shell.launch(key.slice(7))
        else if (key.startsWith("ask:")) { openPage(""); shell.askQuestion(key.slice(4)) }
        else if (key.startsWith("window:")) shell.focusWindow(parseInt(key.slice(7)))
        else if (key === "lock") lockNow()
        else if (key === "control") toggleControl()
        else if (key === "search") openSearch()
        else if (key === "keys") keysOpen = true
        // APVIS for Windows: the power button closes the app (Windows itself is shut down from Windows).
        else if (key === "power" && typeof desktopApp !== "undefined" && desktopApp) Qt.quit()
        else if (key === "power") powerMenuOpen = !powerMenuOpen
        else if (key === "ask") { openPage(""); focusInput.forceActiveFocus() }
        else if (key === "continuity") { openPage(""); shell.askQuestion("what was I doing?") }
        else if (key === "updates") { openPage("settings"); Qt.callLater(() => settingsPage.jump("updates")); shell.checkUpdates() }
        else if (key === "settings:ai") { openPage("settings"); Qt.callLater(() => settingsPage.jump("ai")) }
        else if (key === "files") shell.launch(key)
        else openPage(key)
    }
    Shortcut {
        sequences: [StandardKey.Cancel]
        enabled: (root.answering || root.pageOpen) && !root.searchOpen && !root.controlOpen && !root.keysOpen && !root.powerMenuOpen && topBar.openMenu === ""
        onActivated: { shell.closeAnswer(); root.openPage(""); focusInput.forceActiveFocus() }
    }
    readonly property var missions: shell.missions || []
    // Presentation privacy (V2-13): with a second screen attached, private context
    // (Focus, mission and note text, Memory/Missions pages) stays hidden until the
    // owner confirms the screens are theirs. Resets when the extra screen goes.
    property bool trustedScreens: app
    readonly property int screenCount: Qt.application.screens.length
    readonly property bool sharedDisplay: (screenCount > 1 || previewPage === "shared") && !trustedScreens
    onScreenCountChanged: if (screenCount < 2) trustedScreens = false
    onSharedDisplayChanged: shell.setSharedDisplay(sharedDisplay)
    function priv(text) { return sharedDisplay ? "Hidden · second screen" : text }
    readonly property var activeMissions: missions.filter(m => m.status === "approval_required" || m.status === "running")
    // Tell the owner when something waits for approval while another app is in front.
    property var notifiedApprovals: ({})
    onMissionsChanged: {
        for (const m of missions) {
            if (m.status !== "approval_required" || notifiedApprovals[m.id]) continue
            notifiedApprovals[m.id] = true
            if (Qt.application.state !== Qt.ApplicationActive)
                shell.notify("APVIS needs your approval", m.preview || m.title)
        }
    }
    readonly property var answer: shell.ask || ({ state: "closed" })
    readonly property bool answering: (answer.state || "closed") !== "closed"
    readonly property string modeWord: answering ? "ANSWERING" : state.nucleus_mode === "attention" ? "ATTENTION" :
                                       state.nucleus_mode === "continuity_unknown" ? "CHECK" : "STANDBY"

    // ------------------------------------------------------------ layout (1920×1080 first; scales down)
    readonly property real barH: 40
    readonly property bool tall: height >= 1000
    readonly property real navW: width >= 1600 ? 190 : 168
    readonly property real leftX: navW + 36
    readonly property real leftW: Math.max(290, Math.min(380, width * 0.2))
    readonly property real rightW: Math.max(330, Math.min(460, width * 0.24))
    readonly property real rightX: width - rightW - 22
    readonly property real orbCX: (leftX + leftW + rightX) / 2
    readonly property real dockY: height - 22 - 52                  // APVIS for Windows: the Ask dock along the bottom
    readonly property real statsY: dockY - 18 - 96
    readonly property real orbCY: app ? (barH + 80 + statsY) / 2 : barH + (height - barH) * 0.41
    readonly property real sphereD: app ? Math.min((statsY - barH - 100) * 0.66, (rightX - leftX - leftW) * 0.58)
                                        : Math.min(height * 0.36, (rightX - leftX - leftW) * 0.62)
    readonly property real tilesTop: height * 0.785
    readonly property real gapW: rightX - leftX - leftW          // room between the card columns
    // While an answer is on screen the core grows to the middle and the cards
    // glide out of the way; it eases back when the answer closes.
    property real expand: answering ? 1 : 0
    Behavior on expand { NumberAnimation { duration: 750; easing.type: Easing.InOutCubic } }
    function mix(a, b) { return a + (b - a) * expand }
    readonly property real coreCX: mix(orbCX, width / 2)          // the middle of the screen while answering
    readonly property real coreCY: mix(orbCY, barH + (height - barH) * 0.44)
    // The core item is always its expanded size; only the orb's scale and the
    // centre move, so nothing is repainted while it grows (smooth on the OptiPlex).
    readonly property real bigBox: Math.min((height - barH) * 0.95, (width - leftX) * 0.72)
    readonly property real answerScale: 1.55
    readonly property real orbScale: mix(sphereD * 2 / Math.max(1, bigBox), answerScale)
    readonly property real tileW: Math.min(118, (gapW - 40 - 5 * 14) / 6)

    // ------------------------------------------------------------ background
    Item {
        id: room
        anchors.fill: parent
        layer.enabled: root.lite
        Wallpaper { anchors.fill: parent; centre: Qt.point(root.orbCX / Math.max(1, root.width), root.orbCY / Math.max(1, root.height)) }
        HudGrid { anchors.fill: parent; visible: root.app }      // APVIS for Windows: the blueprint grid of the JARVIS dashboards
    }

    // ------------------------------------------------------------ the core
    Nucleus {
        id: nucleus
        width: root.bigBox; height: width
        orbScale: root.orbScale
        expanded: root.expand
        vsync: !(shell.render || {}).software
        idlePace: root.userIdle ? 12 : 24
        smooth: root.app && !root.userIdle && !root.game.active   // not while a game wants the GPU
        gaming: !!root.game.active
        paused: !root.active && !root.previewWindowed
        answerScale: root.answerScale
        x: root.coreCX - width / 2; y: root.coreCY - height / 2
        opacity: root.pageOpen ? 0 : 1
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }
        scale: root.pageOpen ? 0.92 : 1
        Behavior on scale { NumberAnimation { duration: 340; easing.type: Easing.OutCubic } }
        renderer: (shell.render || {}).renderer || "canvas"
        particles: (shell.render || {}).particles || 900
        reducedMotion: !!(shell.render || {}).reducedMotion
        canvasPoints: shell.canvasPoints
        clock: shell.clock
        motion: (shell.nucleus || {}).motion || ({})
        shape: root.answering ? "aperture" : ((shell.nucleus || {}).shape || "sphere")
        answer: root.answer
        onCloseAnswer: { shell.closeAnswer(); focusInput.forceActiveFocus() }
        onAcceptMemory: (proposalId) => { shell.acceptMemory(proposalId); focusInput.forceActiveFocus() }
        onRejectMemory: (proposalId) => { shell.rejectMemory(proposalId); focusInput.forceActiveFocus() }
        onApproveMission: (missionId, token) => { shell.approveMission(missionId, token); focusInput.forceActiveFocus() }
        onCancelMission: (missionId) => { shell.cancelMission(missionId); focusInput.forceActiveFocus() }
        pin: (shell.nucleus || {}).pin || null
        preview: !!(shell.nucleus || {}).preview
        hasFocus: !!root.focus
        approvals: root.counts.approval_required || 0
        running: root.counts.running || 0
        attention: (root.counts.interrupted || 0) + (root.state.unreadable_task_count || 0)
        rich: !root.lite
        orbMode: root.answer.state === "thinking" ? "thinking" : root.answering ? "answering" :
                 root.state.nucleus_mode === "attention" || root.activeMissions.length ? "attention" : "idle"
        orbWord: root.answer.state === "thinking" ? "THINKING…" : root.answering ? "ANSWERING" :
                 root.activeMissions.length ? "WAITING FOR YOU" : root.state.nucleus_mode === "attention" ? "ATTENTION" : "READY"
        orbWordColour: root.activeMissions.length || root.state.nucleus_mode === "attention" ? Theme.attention : Theme.accent
        modeText: root.answering ? "ANSWERING" : root.state.nucleus_mode === "attention" ? "ATTENTION" : "IDLE"
        modeColor: root.state.nucleus_mode === "attention" ? Theme.attention : Theme.muted
    }

    // ------------------------------------------------------------ Home content (hidden on pages)
    Item {
        id: homeLayer
        anchors.fill: parent
        readonly property bool shown: !root.pageOpen && !intro.active
        opacity: root.pageOpen ? 0 : 1
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }

        // APVIS for Windows: a greeting and the day at a glance instead of the brand block.
        Column {
            visible: root.app
            x: root.leftX; y: root.barH + 34 - 30 * root.expand; spacing: 6
            opacity: (homeLayer.shown ? 1 : 0) * (1 - root.expand)
            Behavior on opacity { enabled: !root.answering && root.expand === 0; NumberAnimation { duration: 700 } }
            readonly property int hour: root.nowTick.getHours()
            readonly property var summary: (typeof shell.intelSummary !== "undefined" && shell.intelSummary) ? shell.intelSummary : ({})
            readonly property int notable: ((summary.severity || {}).high || 0) + ((summary.severity || {}).medium || 0)
            Text { text: parent.hour < 5 ? "Good night" : parent.hour < 12 ? "Good morning" : parent.hour < 18 ? "Good afternoon" : "Good evening"
                   color: Theme.text; font.pixelSize: root.tall ? 38 : 32; font.weight: Font.Light }
            Text { color: Theme.muted; font.pixelSize: 14
                   text: [Qt.formatDateTime(root.nowTick, "dddd d MMMM"),
                          parent.summary.total ? (parent.notable ? parent.notable + " notable reports" : "the world is quiet") : "",
                          root.game.active ? "playing " + (root.game.name || "a game") : ""].filter(x => x).join("   ·   ") }
        }
        BrandBlock {
            visible: !root.app
            x: 34; y: root.barH + 18 - 30 * root.expand
            markSize: root.tall ? 104 : 78
            version: ((shell.updates || {}).installed || "").replace(/^0$/, "") || ""
            opacity: (homeLayer.shown ? 1 : 0) * (1 - root.expand)
            Behavior on opacity { enabled: !root.answering && root.expand === 0; NumberAnimation { duration: 700 } }
        }

        // Left column.
        Column {
            x: root.leftX - (root.leftW + 80) * root.expand; y: root.barH + (root.app ? 140 : root.tall ? 205 : 150); width: root.leftW; spacing: 16
            opacity: 1 - root.expand; visible: opacity > 0.01
            StatusCard { width: parent.width; order: 1; shown: homeLayer.shown; onGo: key => root.act(key) }
            DevicesCard { width: parent.width; order: 2; shown: homeLayer.shown; visible: !root.app; onGo: key => root.act(key) }
            AiCard { width: parent.width; order: 2; shown: homeLayer.shown; visible: root.app; onGo: key => root.act(key) }
            TelemetryCard { width: parent.width; order: 3; shown: homeLayer.shown; visible: root.app; onGo: key => root.act(key) }
        }
        // Right column.
        Column {
            x: root.rightX + (root.rightW + 60) * root.expand; y: root.barH + (root.app ? 140 : root.tall ? 156 : 110); width: root.rightW; spacing: 16
            opacity: 1 - root.expand; visible: opacity > 0.01
            FeedCard { width: parent.width; order: 2; shown: homeLayer.shown; visible: root.app; rows: root.tall ? 6 : 4; onGo: key => root.act(key) }
            TaskCard { width: parent.width; order: 2; shown: homeLayer.shown; visible: !root.app; onGo: key => root.act(key) }
            RouteCard { width: parent.width; order: 3; shown: homeLayer.shown; visible: !root.app; onGo: key => root.act(key) }
            ActivityCard { width: parent.width; order: 4; shown: homeLayer.shown; visible: root.tall && !root.game.available && !root.app; rows: 4; onGo: key => root.act(key) }
            GameCard { width: parent.width; order: 4; shown: homeLayer.shown; visible: !!root.game.available; g: root.game; onGo: key => root.act(key) }
            IntelCard { width: parent.width; order: 5; shown: homeLayer.shown; onGo: key => root.act(key) }
        }

        // Ask bar under the core.
        Item {
            id: askBar
            readonly property real dockW: root.rightX + root.rightW - root.leftX
            width: root.app ? root.mix(dockW - appTiles.width - 16, Math.min(760, dockW)) : Math.min(560, root.gapW - 60)
            height: root.app ? 52 : 50
            x: root.app ? root.mix(root.leftX, root.coreCX - width / 2) : root.coreCX - width / 2
            y: root.app ? root.mix(root.dockY, root.height - height - 26)
                        : root.mix(Math.min(root.orbCY + root.sphereD * 0.66, root.tilesTop - height - 24), root.height - height - 26)
            Chamfer { anchors.fill: parent; cut: 25; fill: Theme.panel; fillOpacity: 0.85; fill2: Theme.bgBottom; fill2Opacity: 0.9
                      stroke: focusInput.activeFocus ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7) : Theme.line
                      edgeGlow: focusInput.activeFocus }
            Glyph { x: 20; anchors.verticalCenter: parent.verticalCenter; width: 18; height: 18; kind: "ask"
                    stroke: focusInput.activeFocus ? Theme.accent : Theme.muted }
            TextField {
                id: focusInput
                x: 50; width: parent.width - x - 58; height: 44
                anchors.verticalCenter: parent.verticalCenter
                placeholderText: "Ask APVIS anything…"
                color: root.pale; placeholderTextColor: root.muted
                selectByMouse: true; font.pixelSize: 15
                verticalAlignment: TextInput.AlignVCenter
                focus: true  // typing on Home goes straight to Ask
                Accessible.name: "Ask APVIS"
                background: Item {}
                onAccepted: { shell.askQuestion(text); text = "" }
                Keys.onEscapePressed: shell.closeAnswer()
                // Typing tells the model scheduler to pause background work (at most every 2 s).
                property real typedAt: 0
                onTextChanged: if (text.length > 0 && Date.now() - typedAt > 2000) { typedAt = Date.now(); shell.ownerTyping() }
            }
            Button {
                id: send
                anchors.right: parent.right; anchors.rightMargin: 7; anchors.verticalCenter: parent.verticalCenter
                width: 38; height: 38
                Accessible.name: "Ask"
                onClicked: { shell.askQuestion(focusInput.text); focusInput.text = "" }
                contentItem: Text { text: "›"; color: Theme.accentInk; font.pixelSize: 24; font.bold: true
                                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 19; color: send.hovered || send.activeFocus ? Theme.text : Theme.accent }
            }
        }
        Text {
            visible: shell.actionError.length > 0
            anchors.horizontalCenter: askBar.horizontalCenter; y: askBar.y - 20
            text: shell.actionError; color: Theme.attention; font.pixelSize: 12
        }

        ActionTiles {
            id: appTiles
            x: root.app ? root.rightX + root.rightW - width : root.orbCX - width / 2
            y: root.app ? root.dockY + 3 + 120 * root.expand : root.tilesTop + 220 * root.expand
            opacity: 1 - root.expand; visible: opacity > 0.01
            tileWidth: root.app ? (root.width >= 1600 ? 128 : 104) : root.tileW
            tileHeight: root.app ? 46 : root.tall ? 88 : 78
            order: 4; shown: homeLayer.shown
            app: root.app
            onChosen: key => {
                if (key === "ask") focusInput.forceActiveFocus()
                else if (key === "brief") shell.askQuestion("catch me up on the news")
                else if (key === "web") { focusInput.text = "search the web for "; focusInput.forceActiveFocus() }
                else if (key.startsWith("page:")) root.act(key)
                else if (key === "search") root.openSearch()
                else if (key === "create") shell.newNote()
                else if (key === "automate") root.openPage("missions")
                else if (key === "analyse") shell.askQuestion("analyse my computer")
                else if (key === "more") root.openPage("apps")
            }
        }
        WorldStats {
            visible: root.app && root.tall
            x: root.leftX + root.leftW + 24; width: root.gapW - 48
            y: root.statsY + 220 * root.expand
            opacity: (1 - root.expand) * (homeLayer.shown ? 1 : 0)
            Behavior on opacity { NumberAnimation { duration: 600 } }
            onGo: key => root.act(key)
        }
        // Apps pinned from the Apps Store, under the tiles.
        PinnedDock {
            x: root.orbCX - width / 2; y: root.tilesTop + (root.tall ? 88 : 78) + 16 + 220 * root.expand
            opacity: (1 - root.expand) * (homeLayer.shown ? 1 : 0); visible: opacity > 0.01 && items.length > 0
            Behavior on opacity { NumberAnimation { duration: 500 } }
            onAct: key => root.act(key)
        }
        TerminalCard {
            id: termCard
            x: 20; width: Math.min(500, root.leftX + root.leftW - 20)
            height: root.tall ? 212 : 190
            y: root.height - height - 22 + (height + 40) * root.expand
            visible: width >= 380 && root.tall && root.expand < 0.99 && !root.app      // below the Devices card only when there is room
            opacity: homeLayer.shown ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 800 } }
            onAction: key => key.startsWith("ask:") ? shell.askQuestion(key.slice(4)) : root.act(key)
            onReleased: focusInput.forceActiveFocus()
        }
    }

    // ------------------------------------------------------------ pages
    Item {
        id: pages
        x: root.leftX; y: root.barH + 16
        width: root.width - x - 22; height: root.height - y - 20
        Column {
            visible: root.sharedDisplay && (root.notesOpen || root.missionsOpen)
            anchors.centerIn: parent; spacing: 12
            Glyph { anchors.horizontalCenter: parent.horizontalCenter; width: 34; height: 34; kind: "brain"; stroke: Theme.attention }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Private — a second screen is connected"; color: root.pale; font.pixelSize: 18 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Your memory and missions stay hidden until you confirm the screens are yours."
                   color: root.muted; font.pixelSize: 12 }
        }
        component PageSlot: Item {
            property bool open: false
            anchors.fill: parent
            opacity: open ? 1 : 0
            visible: open || opacity > 0.01
            Behavior on opacity { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
            transform: Translate { y: open ? 0 : 16; Behavior on y { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } } }
        }
        PageSlot { open: root.settingsOpen; SettingsPage { id: settingsPage; anchors.fill: parent } }
        PageSlot {
            open: root.atlasOpen
            Atlas {
                id: atlasPage
                anchors.fill: parent
                info: shell.atlas || ({ status: "off" })
                aircraftJson: shell.atlasAircraft
                mapJson: shell.atlasMap
                worldJson: shell.atlasWorld
                landJson: shell.worldLand
                dotsJson: shell.earthDots
                onAreaChanged: (lat, lon) => shell.setAtlasArea(lat, lon)
                onVisibleChanged: shell.setAtlasVisible(visible)
                Component.onCompleted: shell.setAtlasVisible(visible)
                onFocusFlight: (callsign, hexId) => shell.focusFlight(callsign, hexId)
            }
        }
        PageSlot { open: root.installOpen; InstallPage { id: installPage; anchors.fill: parent } }
        PageSlot { open: root.devOpen; DeveloperPage { id: devPage; anchors.fill: parent } }
        PageSlot { open: root.systemOpen; SystemPage { anchors.fill: parent } }
        PageSlot { open: root.devicesOpen; DevicesPage { anchors.fill: parent } }
        PageSlot { open: root.gameOpen; GamePage { anchors.fill: parent; g: root.game } }
        PageSlot { open: root.appsOpen; AppsPage { id: appsPage; anchors.fill: parent; onAct: key => root.act(key) } }
        PageSlot { open: root.notesOpen && !root.sharedDisplay
                   MemoryPage { id: memoryPage; anchors.fill: parent; onSuggest: text => root.suggestAsk(text) } }
        PageSlot { open: root.missionsOpen && !root.sharedDisplay
                   MissionsPage { anchors.fill: parent; onSuggest: text => root.suggestAsk(text) } }
    }

    // A reminder or timer that just came due.
    ReminderToast {
        id: reminderToast
        x: (root.width - width) / 2; y: root.barH + 14; z: 50
    }
    // Smoke-test hook: "toast" shows a sample reminder.
    Timer { running: previewPage === "toast"; interval: 800; onTriggered: reminderToast.add("Check the oven", "reminder") }

    // ------------------------------------------------------------ navigation (always there)
    NavRail {
        id: nav
        x: 16; width: root.navW
        y: root.pageOpen ? root.barH + 20 : root.barH + (root.app ? 140 : root.tall ? 205 : 150)
        Behavior on y { NumberAnimation { duration: 420; easing.type: Easing.OutCubic } }
        current: root.currentPage
        badges: ({ missions: root.activeMissions.length > 0, notes: (shell.inbox || []).length > 0,
                   settings: (shell.updates || {}).state === "available" })
        onNavigate: key => root.act(key)
        opacity: intro.active ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: 600 } }
    }

    // Trying from the USB: say so, and offer the installer.
    Item {
        visible: !!(shell.installer || {}).live && !root.pageOpen && !root.sharedDisplay
        width: tryRow.width + 28; height: 40
        x: root.orbCX - width / 2; y: root.barH + 8
        Chamfer { anchors.fill: parent; cut: 20; fill: Theme.panel; fillOpacity: 0.92; stroke: Theme.line }
        Row {
            id: tryRow
            anchors.centerIn: parent; spacing: 12
            Glyph { width: 16; height: 16; kind: "device"; stroke: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
            Text { text: "You're trying APVIS OS from the USB — nothing is saved to this computer"; color: Theme.text; font.pixelSize: 12
                   anchors.verticalCenter: parent.verticalCenter }
            HudButton { width: 110; implicitHeight: 30; caption: "Install…"; tone: "primary"; anchors.verticalCenter: parent.verticalCenter
                        onClicked: root.openPage("install") }
        }
    }

    // Second-screen privacy banner.
    Item {
        visible: root.sharedDisplay
        width: bannerRow.width + 28; height: 40
        x: (root.width - width) / 2; y: root.barH + 8
        Chamfer { anchors.fill: parent; cut: 20; fill: Theme.panel; fillOpacity: 0.95; stroke: Theme.attention }
        Row {
            id: bannerRow
            anchors.centerIn: parent; spacing: 12
            Glyph { width: 16; height: 16; kind: "device"; stroke: Theme.attention; anchors.verticalCenter: parent.verticalCenter }
            Text { text: "Second screen connected — private details hidden"; color: root.pale; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
            HudButton { width: 150; caption: "They're my screens"; onClicked: root.trustedScreens = true; anchors.verticalCenter: parent.verticalCenter }
        }
    }

    // Terminal from Home with keys compact keyboards can press (Win+Enter is
    // awkward on Rii mini keyboards): Ctrl+Alt+T or Ctrl+Alt+Del.
    Shortcut { sequences: ["Ctrl+Alt+T", "Ctrl+Alt+Del", "Ctrl+Alt+Backspace"]; enabled: !root.locked; onActivated: shell.launch("terminal") }

    // ------------------------------------------------------------ menu bar
    MouseArea { anchors.fill: parent; visible: topBar.openMenu !== ""; onClicked: topBar.openMenu = "" }
    Shortcut { sequences: [StandardKey.Cancel]; enabled: topBar.openMenu !== ""; onActivated: topBar.openMenu = "" }
    TopBar {
        id: topBar
        width: root.width
        now: root.nowTick
        powerOpen: root.powerMenuOpen
        onAction: key => root.act(key)
        opacity: intro.active ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: 600 } }
    }

    // ------------------------------------------------------------ power menu (top right)
    property bool powerMenuOpen: previewPage === "power"
    Shortcut { sequences: [StandardKey.Cancel]; enabled: root.powerMenuOpen; onActivated: root.powerMenuOpen = false }
    MouseArea { anchors.fill: parent; visible: root.powerMenuOpen; onClicked: root.powerMenuOpen = false }
    Item {
        id: powerMenu
        visible: root.powerMenuOpen || opacity > 0.01
        opacity: root.powerMenuOpen ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        transform: Translate { y: root.powerMenuOpen ? 0 : -8; Behavior on y { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } } }
        width: powerMenuRow.width + 150; height: powerMenuCol.height + 32
        x: root.width - width - 14; y: root.barH + 6
        MouseArea { anchors.fill: parent }
        Chamfer { anchors.fill: parent; cut: 14; fill: Theme.panel; fillOpacity: 0.97; fill2: Theme.bgBottom; fill2Opacity: 0.97
                  stroke: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.4); edgeGlow: true }
        Column {
            id: powerMenuCol
            x: 16; y: 16; spacing: 12
            Text { text: "Power"; color: Theme.text; font.pixelSize: 15 }
            Row {
                spacing: 6
                HudButton { visible: !shell.guest; width: 112; glyph: "key"; caption: "Lock"; onClicked: { root.powerMenuOpen = false; root.lockNow() } }
                PowerButtons { id: powerMenuRow; buttonWidth: 112 }
            }
            Text { text: (shell.control || {}).message || "Press a button twice to confirm."; color: Theme.muted; font.pixelSize: 11 }
        }
    }

    // ------------------------------------------------------------ Control Centre (owner concept, screen 07)
    // Real state only; every change is read back.
    property bool controlOpen: previewPage === "control"
    function toggleControl() {
        if (locked) return
        controlOpen = !controlOpen
        if (controlOpen) { shell.refreshControl(); controlFirst.forceActiveFocus() } else focusInput.forceActiveFocus()
    }
    Shortcut { sequences: [StandardKey.Cancel]; enabled: root.controlOpen && !root.keysOpen; onActivated: root.toggleControl() }
    readonly property var ctl: shell.control || ({})
    readonly property var ctlSound: (ctl.state || {}).sound || ({})
    // The sound state arrives after the panel opens: move focus to the slider then.
    onCtlSoundChanged: if (controlOpen && ctlSound.available && dndButton.activeFocus) volSlider.forceActiveFocus()
    readonly property var ctlWifi: (ctl.state || {}).wifi || ({})
    Timer { interval: 5000; repeat: true; running: root.controlOpen; onTriggered: shell.refreshControl() }
    MouseArea { anchors.fill: parent; visible: root.controlOpen; onClicked: root.controlOpen = false }
    Item {
        id: controlPanel
        opacity: root.controlOpen ? 1 : 0
        visible: root.controlOpen || opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        transform: Translate { y: root.controlOpen ? 0 : -10; Behavior on y { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } } }
        scale: root.controlOpen ? 1 : 0.97
        Behavior on scale { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        width: 440; height: controlCol.height + 36
        x: root.width - width - 14; y: root.barH + 6
        MouseArea { anchors.fill: parent }
        Chamfer { anchors.fill: parent; cut: 16; fill: Theme.panel; fillOpacity: 0.97; fill2: Theme.bgBottom; fill2Opacity: 0.97
                  stroke: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.4); edgeGlow: true }
        // Keyboard entry point (the slider when sound exists, else the first switch).
        Item { id: controlFirst; focus: false
               onActiveFocusChanged: if (activeFocus) (volSlider.visible ? volSlider : wifiButton.visible ? wifiButton : dndButton).forceActiveFocus() }
        component StatTileSmall: Item {
            property string glyph: ""
            property string label: ""
            property string value: ""
            property real fraction: -1
            width: (controlCol.width - 30) / 4; height: 76
            Chamfer { anchors.fill: parent; cut: 10; fill: Theme.raised; fillOpacity: 0.7; stroke: Theme.line }
            Text { x: 10; y: 9; text: parent.label; color: Theme.muted; font.pixelSize: 11 }
            Glyph { x: 10; y: 34; width: 16; height: 16; kind: parent.glyph; stroke: Theme.accent }
            Text { x: 32; y: 32; text: parent.value; color: Theme.text; font.pixelSize: 15 }
            Rectangle { visible: parent.fraction >= 0; x: 10; y: parent.height - 12; width: parent.width - 20; height: 3; radius: 1.5; color: Theme.sheen(0.08)
                        Rectangle { height: parent.height; radius: 1.5; width: parent.width * Math.max(0, Math.min(1, parent.parent.fraction)); color: Theme.accent } }
        }
        Column {
            id: controlCol
            x: 18; y: 18; width: parent.width - 36; spacing: 12
            Row {
                width: parent.width
                Text { text: "Control Centre"; color: Theme.text; font.pixelSize: 16; width: parent.width - 40 }
                Text { text: Qt.formatDateTime(root.nowTick, "HH:mm"); color: Theme.muted; font.pixelSize: 13 }
            }
            Row {
                spacing: 10
                StatTileSmall { glyph: "cpu"; label: "CPU"; value: root.sys.available ? root.sys.cpu + "%" : "—"; fraction: root.sys.available ? root.sys.cpu / 100 : -1 }
                StatTileSmall { glyph: "memory"; label: "Memory"; value: root.sys.available ? root.sys.memory + "%" : "—"; fraction: root.sys.available ? root.sys.memory / 100 : -1 }
                StatTileSmall { glyph: "storage"; label: "Storage"; value: root.sys.disk !== null && root.sys.disk !== undefined ? root.sys.disk + "%" : "—"
                                fraction: root.sys.disk !== null && root.sys.disk !== undefined ? root.sys.disk / 100 : -1 }
                StatTileSmall { glyph: "clock"; label: "Uptime"; value: root.sys.boot_epoch_ms ? (function () {
                                    const s = Math.floor((root.nowTick.getTime() - root.sys.boot_epoch_ms) / 1000)
                                    return Math.floor(s / 3600) + "h " + Math.floor(s % 3600 / 60) + "m" })() : "—" }
            }
            // Sound.
            Item {
                width: parent.width; height: 26
                Glyph { width: 16; height: 16; kind: "volume"; stroke: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                Text { x: 26; text: "Sound"; color: Theme.text; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; color: Theme.muted; font.pixelSize: 12
                       text: !root.ctlSound.available ? (root.ctlSound.detail || "Checking…") : root.ctlSound.muted ? "Muted" : root.ctlSound.volume + "%"
                       width: parent.width - 120; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight }
            }
            Item {
                visible: !!root.ctlSound.available
                width: parent.width; height: 40
                Slider {
                    id: volSlider
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 100; from: 0; to: 100; stepSize: 1
                    value: root.ctlSound.volume || 0
                    Accessible.name: "Volume"
                    onMoved: volDebounce.restart()
                    background: Item {
                        x: volSlider.leftPadding; y: volSlider.topPadding + volSlider.availableHeight / 2 - 2
                        width: volSlider.availableWidth; height: 4
                        Rectangle { anchors.fill: parent; radius: 2; color: Theme.raised; border.color: Theme.line }
                        Rectangle { width: volSlider.visualPosition * parent.width; height: parent.height; radius: 2; color: Theme.accent }
                    }
                    handle: Rectangle {
                        x: volSlider.leftPadding + volSlider.visualPosition * (volSlider.availableWidth - width)
                        y: volSlider.topPadding + volSlider.availableHeight / 2 - height / 2
                        width: 16; height: 16; radius: 8; color: Theme.text
                        border.width: volSlider.activeFocus ? 3 : 1; border.color: Theme.accent
                    }
                    Timer { id: volDebounce; interval: 180; onTriggered: shell.setVolume(Math.round(volSlider.value)) }
                }
                HudButton { anchors.right: parent.right; width: 90; caption: root.ctlSound.muted ? "Unmute" : "Mute"; onClicked: shell.setMuted(!root.ctlSound.muted) }
            }
            // Now playing (any MPRIS player: Spotify, VLC, the browser…)
            Item {
                readonly property var m: (ctl.state || {}).media || ({})
                visible: !!m.available && !!m.title
                width: parent.width; height: visible ? 50 : 0
                Glyph { width: 16; height: 16; kind: "volume"; stroke: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                Column {
                    x: 26; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 26 - 132
                    Text { width: parent.width; elide: Text.ElideRight; text: parent.parent.m.title || ""; color: Theme.text; font.pixelSize: 13 }
                    Text { width: parent.width; elide: Text.ElideRight; color: Theme.muted; font.pixelSize: 11
                           text: (parent.parent.m.artist ? parent.parent.m.artist + "  ·  " : "") + (parent.parent.m.player || "") }
                }
                Row {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 4
                    HudButton { width: 40; implicitHeight: 32; caption: "⏮"; onClicked: shell.mediaControl("previous"); Accessible.name: "Previous" }
                    HudButton { width: 44; implicitHeight: 32; tone: "primary"; caption: parent.parent.m.playing ? "⏸" : "▶"
                                onClicked: shell.mediaControl("play-pause"); Accessible.name: parent.parent.m.playing ? "Pause" : "Play" }
                    HudButton { width: 40; implicitHeight: 32; caption: "⏭"; onClicked: shell.mediaControl("next"); Accessible.name: "Next" }
                }
            }
            Item {
                visible: !(root.ctlWifi.available && root.ctlWifi.hasWifi)
                width: parent.width; height: 26
                Glyph { width: 16; height: 16; kind: "wifi"; stroke: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                Text { x: 26; text: "Network"; color: Theme.text; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; color: Theme.muted; font.pixelSize: 12
                       text: !root.ctlWifi.available ? (root.ctlWifi.detail || "Checking…") : (root.ctlWifi.wired ? "Wired · " + root.ctlWifi.wired : "No Wi-Fi adapter")
                       width: parent.width - 120; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight }
            }
            HudToggle {
                id: wifiButton
                visible: !!root.ctlWifi.available && !!root.ctlWifi.hasWifi
                width: parent.width; on: !!root.ctlWifi.on; caption: "Wi-Fi"
                detail: !root.ctlWifi.on ? "Off" : (root.ctlWifi.network || "On · not connected")
                onClicked: shell.setWifi(!root.ctlWifi.on)
            }
            HudToggle { id: dndButton; width: parent.width; on: !!(shell.settings || {}).dnd; caption: "Do not disturb"
                        detail: "Hides notifications. Approvals always get through."
                        onClicked: shell.setDoNotDisturb(!(shell.settings || {}).dnd) }
            HudToggle { width: parent.width; on: !!(shell.render || {}).reducedMotion; caption: "Reduce motion"
                        detail: "Stills the core's smoke and the effects."
                        onClicked: shell.setReducedMotion(!(shell.render || {}).reducedMotion) }
            Text {
                width: parent.width; wrapMode: Text.WordWrap; font.pixelSize: 11
                visible: text.length > 0
                text: root.ctl.message || ""
                color: root.ctl.ok === false ? Theme.attention : Theme.accent
            }
            Row {
                spacing: 8
                HudButton { width: (controlCol.width - 16) / 3; glyph: "screen"; caption: "Displays"; onClicked: shell.launch("displays") }
                HudButton { width: (controlCol.width - 16) / 3; glyph: "volume"; caption: "Audio"; onClicked: shell.launch("sound") }
                HudButton { width: (controlCol.width - 16) / 3; glyph: "wifi"; caption: "Network"; onClicked: shell.launch("network") }
            }
            Text { text: Theme.label("POWER"); color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 2; topPadding: 2 }
            PowerButtons { buttonWidth: (controlCol.width - 18) / 4 }
        }
    }

    // ------------------------------------------------------------ shortcuts (F1)
    // Mirrors /etc/apvis-os/labwc/rc.xml and the Home shortcuts; keep them in step.
    property bool keysOpen: previewPage === "keys"
    Shortcut { sequences: ["F1"]; enabled: !root.locked; onActivated: root.keysOpen = !root.keysOpen }
    Shortcut { sequences: [StandardKey.Cancel]; enabled: root.keysOpen; onActivated: root.keysOpen = false }
    Rectangle {
        anchors.fill: parent; color: Theme.shade(0.55)
        opacity: root.keysOpen ? 1 : 0; visible: root.keysOpen || opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: 180 } }
        MouseArea { anchors.fill: parent; onClicked: root.keysOpen = false }
    }
    Item {
        opacity: root.keysOpen ? 1 : 0
        visible: root.keysOpen || opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        scale: root.keysOpen ? 1 : 0.97
        Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        width: Math.min(640, root.width - 80); height: keysCol.height + 44
        x: (root.width - width) / 2; y: (root.height - height) / 2
        Chamfer { anchors.fill: parent; cut: 16; fill: Theme.panel; fillOpacity: 0.97; fill2: Theme.bgBottom; fill2Opacity: 0.97
                  stroke: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.4); edgeGlow: true }
        Column {
            id: keysCol
            x: 26; y: 22; width: parent.width - 52; spacing: 7
            Text { text: "Keyboard shortcuts"; color: Theme.text; font.pixelSize: 17; bottomPadding: 8 }
            Repeater {
                model: [
                    ["Ctrl + K", "Search this computer"], ["F1", "This list"], ["Esc", "Close a panel, page or answer"],
                    ["Type on Home", "Ask APVIS"], ["Win + P", "Bring APVIS Home back"],
                    ["Win + Space", "All apps"], ["Win + E", "Files"], ["Win + Enter  or  Ctrl + Alt + T / Del", "Terminal"],
                    ["APVIS logo", "Home and every open app"], ["Alt + Tab", "Switch window"], ["Alt + F4", "Close window"],
                    ["Win + D", "Show Home (again: the windows come back)"], ["Win + ↑ / ↓", "Maximise / minimise window"],
                    ["Win + ← / →", "Previous / next workspace"], ["Win + Shift + ← / →", "Move window to that workspace"]
                ]
                delegate: Item {
                    required property var modelData
                    width: keysCol.width; height: 26
                    Rectangle { width: keyText.width + 18; height: 24; radius: 6; color: Theme.raised; border.color: Theme.line
                        Text { id: keyText; anchors.centerIn: parent; text: modelData[0]; color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 11 } }
                    Text { x: 250; anchors.verticalCenter: parent.verticalCenter; text: modelData[1]; color: root.pale; font.pixelSize: 13 }
                }
            }
        }
    }

    // ------------------------------------------------------------ search (Ctrl+K)
    // One local search: apps, pages, settings, notes, missions and home files.
    // Nothing leaves this computer; only listed results can be opened.
    property bool searchOpen: false
    function openSearch() { if (locked) return; searchOpen = true; searchField.text = ""; shell.search(""); searchField.forceActiveFocus() }
    function closeSearch() { searchOpen = false; focusInput.forceActiveFocus() }
    function openHit(i) {
        const r = (shell.searchResults || [])[i]
        if (!r) return
        closeSearch()
        shell.openResult(r.kind, r.key)
    }
    function hitGlyph(r) {
        if (r.kind === "page") return r.key === "home" ? "home" : r.key === "missions" ? "mission" : r.key
        return { app: "apps", setting: "settings", note: "notes", mission: "mission", file: "files", folder: "files" }[r.kind] || "search"
    }
    Shortcut { sequences: ["Ctrl+K", "Ctrl+F"]; onActivated: root.searchOpen ? root.closeSearch() : root.openSearch() }
    Rectangle {
        anchors.fill: parent; color: Theme.shade(0.55)
        opacity: root.searchOpen ? 1 : 0; visible: root.searchOpen || opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: 180 } }
        MouseArea { anchors.fill: parent; onClicked: root.closeSearch() }
    }
    Item {
        id: searchPanel
        opacity: root.searchOpen ? 1 : 0
        visible: root.searchOpen || opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        scale: root.searchOpen ? 1 : 0.97
        Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        width: Math.min(680, root.width - 80)
        height: 62 + (hitList.count ? hitList.height + 10 : searchField.text.length ? 40 : 0) + 26
        x: (root.width - width) / 2; y: Math.max(70, root.height * 0.14)
        MouseArea { anchors.fill: parent }  // clicks inside do not close it
        Chamfer { anchors.fill: parent; cut: 16; fill: Theme.panel; fillOpacity: 0.97; fill2: Theme.bgBottom; fill2Opacity: 0.97
                  stroke: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.45); edgeGlow: true }
        Glyph { x: 20; y: 21; width: 20; height: 20; kind: "search"; stroke: Theme.accent }
        TextField {
            id: searchField
            x: 50; y: 9; width: parent.width - 66; height: 44
            placeholderText: "Search apps, files, notes, settings…"
            color: root.pale; placeholderTextColor: root.muted
            font.pixelSize: 16; selectByMouse: true
            background: Item {}
            Accessible.name: "Search this computer"
            onTextChanged: { hitList.currentIndex = 0; searchDebounce.restart() }
            Keys.onDownPressed: hitList.incrementCurrentIndex()
            Keys.onUpPressed: hitList.decrementCurrentIndex()
            Keys.onEscapePressed: root.closeSearch()
            onAccepted: root.openHit(hitList.currentIndex)
        }
        Timer { id: searchDebounce; interval: 120; onTriggered: shell.search(searchField.text) }
        Rectangle { x: 14; y: 58; width: parent.width - 28; height: 1; color: Theme.line }
        ListView {
            id: hitList
            x: 10; y: 66; width: parent.width - 20
            height: Math.min(count, 8) * 46
            clip: true; currentIndex: 0
            model: shell.searchResults || []
            delegate: Item {
                id: hit
                required property var modelData
                required property int index
                readonly property bool current: ListView.isCurrentItem
                width: ListView.view.width; height: 46
                Rectangle { anchors.fill: parent; anchors.margins: 2; radius: 8
                            color: hit.current ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.14) : hitMouse.containsMouse ? Theme.hover : "transparent"
                            border.width: hit.current ? 1 : 0; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.5) }
                Glyph { x: 14; anchors.verticalCenter: parent.verticalCenter; width: 18; height: 18; kind: root.hitGlyph(hit.modelData); stroke: hit.current ? Theme.accent : Theme.muted }
                Column {
                    x: 46; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 46 - 90; spacing: 2
                    Text { width: parent.width; text: hit.modelData.title; color: Theme.text; font.pixelSize: 14; elide: Text.ElideRight }
                    Text { width: parent.width; text: hit.modelData.detail; color: Theme.muted; font.pixelSize: 11; elide: Text.ElideMiddle }
                }
                Text { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                       text: Theme.upper(hit.modelData.kind); color: hit.current ? Theme.accent : Theme.muted
                       font.family: Theme.monoFont; font.pixelSize: 9; font.letterSpacing: Theme.caps ? 1.2 : 0.3 }
                MouseArea { id: hitMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.openHit(hit.index) }
                Accessible.role: Accessible.ListItem
                Accessible.name: hit.modelData.title + ", " + hit.modelData.kind
            }
        }
        Text {
            visible: searchField.text.length > 0 && hitList.count === 0
            x: 50; y: 70; text: "Nothing on this computer matches."
            color: Theme.muted; font.pixelSize: 13
        }
        Text {
            anchors.bottom: parent.bottom; anchors.bottomMargin: 8; x: 20
            text: "↑ ↓ choose   ·   Enter open   ·   Esc close   ·   F1 shortcuts   ·   this computer only"
            color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 9; font.letterSpacing: 0.8
        }
    }

    // ------------------------------------------------------------ awakening and goodbye
    IntroOverlay {
        id: intro
        anchors.fill: parent
        active: previewPage === "" && !previewNoIntro
        still: root.calm
        onFinished: root.locked ? lockScreen.engage() : focusInput.forceActiveFocus()
    }
    LockOverlay {
        id: lockScreen
        anchors.fill: parent
        now: root.nowTick
        onUnlocked: focusInput.forceActiveFocus()
    }
    GoodbyeOverlay {
        id: goodbye
        anchors.fill: parent
        onProceed: action => shell.power(action)
    }

    // A picture the owner asked for ("show me a picture of Paris"), from Wikimedia Commons with its credit.
    Item {
        id: pictureCard
        readonly property var pic: (root.answer && root.answer.state !== "closed" && root.answer.picture) || null
        visible: pic !== null
        anchors.fill: parent
        z: 50
        MouseArea { anchors.fill: parent; onClicked: shell.closeAnswer() }
        Rectangle { anchors.fill: parent; color: Theme.shade(0.55) }
        Item {
            id: frame
            width: Math.min(parent.width * 0.62, 1100); height: Math.min(parent.height * 0.72, 760)
            anchors.centerIn: parent
            MouseArea { anchors.fill: parent }
            Chamfer { anchors.fill: parent; cut: 16; fill: Theme.panel; fillOpacity: 0.96; fill2: Theme.bgBottom; fill2Opacity: 0.96
                      stroke: Theme.accent; edgeGlow: true; glowColour: Theme.accent }
            Image {
                id: photo
                x: 18; y: 18; width: parent.width - 36; height: parent.height - 110
                source: pictureCard.pic ? pictureCard.pic.url : ""
                fillMode: Image.PreserveAspectFit; asynchronous: true; smooth: true; mipmap: true
                sourceSize.width: 1280
            }
            Column {
                x: 22; anchors.bottom: parent.bottom; anchors.bottomMargin: 18; width: parent.width - 120; spacing: 4
                Text { width: parent.width; text: pictureCard.pic ? pictureCard.pic.caption : ""; color: Theme.text
                       font.pixelSize: 15; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.WordWrap
                       font.family: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family }
                Text { width: parent.width; elide: Text.ElideRight; color: Theme.muted; font.pixelSize: 11
                       text: pictureCard.pic ? "Wikimedia Commons" + (pictureCard.pic.credit ? " · " + pictureCard.pic.credit : "") : "" }
            }
            HudButton { anchors.right: parent.right; anchors.rightMargin: 18; anchors.bottom: parent.bottom; anchors.bottomMargin: 18
                        width: 90; implicitHeight: 32; caption: "Close"; onClicked: shell.closeAnswer() }
        }
    }
}
