import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebEngine
import "../theme"

// APVIS Browser (apvis_os/browser.py): tabs, an address bar that also searches (DuckDuckGo),
// tracker blocking with a live count, downloads, permission prompts and "Ask APVIS" about
// the open page with the local models. Dark glass chrome in the owner's concept style.
ApplicationWindow {
    id: win
    visible: true
    width: 1400; height: 880
    minimumWidth: 760; minimumHeight: 480
    color: Theme.bgBottom
    title: (current && current.title ? current.title + "  —  " : "") + "APVIS Browser"
    readonly property Item current: stack.count > 0 ? repeater.itemAt(stack.currentIndex) : null

    // One persistent, private-by-default profile for every tab (browser.py adds the tracker
    // blocker and the third-party cookie filter to it).
    WebEngineProfile {
        id: webProfile
        objectName: "apvisProfile"
        storageName: "apvis"
        offTheRecord: false
        Component.onCompleted: browser.attachProfile(webProfile)
        persistentStoragePath: browser.dataPath + "/profile"
        cachePath: browser.dataPath + "/cache"
        httpCacheType: WebEngineProfile.DiskHttpCache
        persistentCookiesPolicy: WebEngineProfile.AllowPersistentCookies
        downloadPath: browser.downloadPath
        onDownloadRequested: download => { download.accept(); downloads.add(download) }
    }

    ListModel { id: tabModel }
    function newTab(url, focusAddress) {
        tabModel.append({ startUrl: url || "" })
        stack.currentIndex = tabModel.count - 1
        if (focusAddress !== false && !url) Qt.callLater(() => { address.forceActiveFocus(); address.selectAll() })
        return repeater.itemAt(tabModel.count - 1)
    }
    function closeTab(i) {
        if (tabModel.count <= 1) { Qt.quit(); return }
        tabModel.remove(i)
        stack.currentIndex = Math.min(stack.currentIndex, tabModel.count - 1)
    }
    function go(text) {
        const url = browser.normalize(text)
        if (!url || !current) return
        current.open(url)
    }
    function askPage(question) {
        if (!current || !current.view.url.toString()) return
        askPanel.open = true
        current.view.runJavaScript("(document.body ? document.body.innerText : '').slice(0, 20000)",
            text => browser.ask(question || "", current.view.title, current.view.url.toString(), text || ""))
    }
    Component.onCompleted: newTab(startUrl, true)
    // Development hook (APVIS_BROWSER_SMOKE_JS): "ask" asks about the page, "go:<text>" opens an address.
    property string smokeStep: ""
    onSmokeStepChanged: { if (smokeStep === "ask") askPage(""); else if (smokeStep.startsWith("go:")) go(smokeStep.slice(3)) }

    Shortcut { sequence: "Ctrl+T"; onActivated: win.newTab("") }
    Shortcut { sequence: "Ctrl+W"; onActivated: win.closeTab(stack.currentIndex) }
    Shortcut { sequence: "Ctrl+L"; onActivated: { address.forceActiveFocus(); address.selectAll() } }
    Shortcut { sequences: ["Ctrl+R", "F5"]; onActivated: if (current) current.view.reload() }
    Shortcut { sequence: "Alt+Left"; onActivated: if (current) current.view.goBack() }
    Shortcut { sequence: "Alt+Right"; onActivated: if (current) current.view.goForward() }
    Shortcut { sequence: "Ctrl+Tab"; onActivated: stack.currentIndex = (stack.currentIndex + 1) % tabModel.count }
    Shortcut { sequence: "Ctrl+Shift+Tab"; onActivated: stack.currentIndex = (stack.currentIndex + tabModel.count - 1) % tabModel.count }
    Shortcut { sequence: "Ctrl+Shift+A"; onActivated: win.askPage("") }
    Shortcut { sequence: "F11"; onActivated: win.visibility === Window.FullScreen ? win.showNormal() : win.showFullScreen() }
    Shortcut { sequences: ["Ctrl+=", "Ctrl++"]; onActivated: if (current) current.view.zoomFactor = Math.min(3, current.view.zoomFactor + 0.1) }
    Shortcut { sequence: "Ctrl+-"; onActivated: if (current) current.view.zoomFactor = Math.max(0.3, current.view.zoomFactor - 0.1) }
    Shortcut { sequence: "Ctrl+0"; onActivated: if (current) current.view.zoomFactor = 1 }
    Shortcut { sequence: "Escape"; enabled: askPanel.open; onActivated: { askPanel.open = false; browser.closeAnswer() } }

    component ChromeButton: AbstractButton {
        id: cb
        property string label: ""
        property string tip: ""
        implicitWidth: 34; implicitHeight: 34
        hoverEnabled: true
        ToolTip.visible: hovered && tip.length > 0; ToolTip.delay: 500; ToolTip.text: tip
        Accessible.name: tip || label
        background: Rectangle { radius: 8; color: cb.down ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.2)
                                                     : cb.hovered && cb.enabled ? Theme.sheen(0.07) : "transparent" }
        contentItem: Text { text: cb.label; color: cb.enabled ? Theme.text : Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, 0.3)
                            font.pixelSize: 17; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
    }

    // ------------------------------------------------------------ tab strip
    Rectangle {
        id: strip
        width: parent.width; height: 42
        color: Theme.shade(0.55)
        Row {
            x: 8; y: 6; height: 36; spacing: 4
            ApvisMark { width: 22; height: 20; anchors.verticalCenter: parent.verticalCenter; glow: 0.6 }
            Item { width: 6; height: 1 }
            Repeater {
                model: tabModel
                delegate: AbstractButton {
                    id: tabBtn
                    required property int index
                    readonly property Item page: repeater.itemAt(index)
                    readonly property bool sel: stack.currentIndex === index
                    width: Math.max(120, Math.min(240, (strip.width - 120) / Math.max(1, tabModel.count))); height: 36
                    hoverEnabled: true
                    onClicked: stack.currentIndex = index
                    Accessible.name: page ? page.title : "Tab"
                    background: Rectangle {
                        radius: 9; color: tabBtn.sel ? Theme.panel : tabBtn.hovered ? Theme.sheen(0.05) : "transparent"
                        border.width: tabBtn.sel ? 1 : 0; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.45)
                        Rectangle { visible: tabBtn.sel; x: 12; width: parent.width - 24; height: 2; radius: 1; color: Theme.accent }
                    }
                    contentItem: Item {
                        Image { id: fav; x: 10; anchors.verticalCenter: parent.verticalCenter; width: 16; height: 16
                                source: tabBtn.page && tabBtn.page.view.icon ? tabBtn.page.view.icon : ""; visible: status === Image.Ready }
                        Text { visible: !fav.visible; x: 10; anchors.verticalCenter: parent.verticalCenter; text: tabBtn.page && tabBtn.page.loading ? "◌" : "◆"
                               color: Theme.accent; font.pixelSize: 11 }
                        Text { x: 34; width: parent.width - 34 - 30; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                               text: tabBtn.page ? (tabBtn.page.title || "New tab") : ""; color: tabBtn.sel ? Theme.text : Theme.muted; font.pixelSize: 13 }
                        AbstractButton {
                            anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                            width: 22; height: 22; visible: tabBtn.hovered || tabBtn.sel
                            onClicked: win.closeTab(tabBtn.index)
                            Accessible.name: "Close tab"
                            background: Rectangle { radius: 11; color: parent.hovered ? Theme.sheen(0.12) : "transparent" }
                            contentItem: Text { text: "✕"; color: Theme.muted; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        }
                    }
                }
            }
            ChromeButton { label: "+"; tip: "New tab (Ctrl+T)"; onClicked: win.newTab(""); anchors.verticalCenter: parent.verticalCenter }
        }
    }

    // ------------------------------------------------------------ toolbar
    Rectangle {
        id: toolbar
        y: strip.height; width: parent.width; height: 52
        color: Theme.panel
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 6
            ChromeButton { label: "←"; tip: "Back (Alt+Left)"; enabled: !!current && current.view.canGoBack; onClicked: current.view.goBack() }
            ChromeButton { label: "→"; tip: "Forward (Alt+Right)"; enabled: !!current && current.view.canGoForward; onClicked: current.view.goForward() }
            ChromeButton { label: current && current.loading ? "✕" : "↻"; tip: current && current.loading ? "Stop" : "Reload (Ctrl+R)"
                           onClicked: current.loading ? current.view.stop() : current.view.reload() }
            // Address + search
            Item {
                Layout.fillWidth: true; Layout.preferredHeight: 36
                Rectangle {
                    anchors.fill: parent; radius: 10
                    color: Theme.sheen(address.activeFocus ? 0.07 : 0.04)
                    border.width: address.activeFocus ? 1.5 : 1
                    border.color: address.activeFocus ? Theme.accent : Theme.line
                }
                Text {
                    id: lock
                    x: 12; anchors.verticalCenter: parent.verticalCenter
                    readonly property string u: current ? current.view.url.toString() : ""
                    text: u.startsWith("https://") ? "◆" : u.startsWith("http://") ? "!" : "⌕"
                    color: u.startsWith("http://") ? Theme.attention : Theme.muted; font.pixelSize: 13
                    ToolTip.visible: lockHover.containsMouse; ToolTip.text: u.startsWith("https://") ? "Secure connection" : u.startsWith("http://") ? "Not secure: this page isn't encrypted" : "Search or type an address"
                    MouseArea { id: lockHover; anchors.fill: parent; hoverEnabled: true }
                }
                TextField {
                    id: address
                    anchors.fill: parent; anchors.leftMargin: 32; anchors.rightMargin: shield.width + 12
                    background: null
                    color: Theme.text; selectedTextColor: Theme.bgBottom; selectionColor: Theme.accent
                    placeholderText: "Search with DuckDuckGo or type an address"; placeholderTextColor: Theme.muted
                    font.pixelSize: 14; verticalAlignment: TextInput.AlignVCenter
                    Accessible.name: "Address and search"
                    // Show the page address unless the owner is typing.
                    Binding on text { when: !address.activeFocus; value: current ? (current.view.url.toString() === "" ? "" : current.view.url.toString()) : ""; restoreMode: Binding.RestoreNone }
                    onAccepted: { win.go(text); current.view.forceActiveFocus() }
                    onActiveFocusChanged: if (activeFocus) Qt.callLater(selectAll)
                }
                // Trackers blocked on this site
                Rectangle {
                    id: shield
                    anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                    readonly property int n: current && browser.blockedTotal >= 0 ? browser.blockedOn(current.view.url.toString().replace(/^[a-z]+:\/\//, "").split("/")[0]) : 0
                    width: shieldText.implicitWidth + 16; height: 24; radius: 12
                    color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, n > 0 ? 0.14 : 0.05)
                    border.width: 1; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, n > 0 ? 0.5 : 0.2)
                    Text { id: shieldText; anchors.centerIn: parent; text: "⊘ " + shield.n; color: shield.n > 0 ? Theme.accent : Theme.muted; font.pixelSize: 11 }
                    ToolTip.visible: shieldHover.containsMouse
                    ToolTip.text: shield.n + " tracker request" + (shield.n === 1 ? "" : "s") + " blocked on this site · " + browser.blockedTotal + " this session"
                    MouseArea { id: shieldHover; anchors.fill: parent; hoverEnabled: true }
                }
                // Loading progress along the bottom of the address bar
                Rectangle {
                    visible: !!current && current.loading
                    anchors.bottom: parent.bottom; x: 10; height: 2; radius: 1; color: Theme.accent
                    width: (parent.width - 20) * (current ? current.view.loadProgress / 100 : 0)
                    Behavior on width { NumberAnimation { duration: 200 } }
                }
            }
            HudButton {
                Layout.preferredWidth: 150; implicitHeight: 36
                glyph: "brain"; tone: askPanel.open ? "selected" : "primary"; caption: "Ask APVIS"
                enabled: !!current && current.view.url.toString() !== ""
                onClicked: askPanel.open ? (askPanel.open = false) : win.askPage("")
                ToolTip.visible: hovered; ToolTip.delay: 500; ToolTip.text: "Ask about this page with your local AI (Ctrl+Shift+A)"
            }
            ChromeButton { label: "⤓"; tip: "Downloads"; onClicked: downloads.shown = !downloads.shown
                           Rectangle { visible: downloads.active > 0; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 4
                                       width: 8; height: 8; radius: 4; color: Theme.accent } }
        }
    }

    // ------------------------------------------------------------ pages
    StackLayout {
        id: stack
        anchors.top: toolbar.bottom; anchors.bottom: parent.bottom
        anchors.left: parent.left; anchors.right: askPanel.left
        Repeater {
            id: repeater
            model: tabModel
            delegate: Item {
                id: tab
                required property int index
                required property string startUrl
                property alias view: web
                readonly property bool loading: web.loading
                readonly property bool home: web.url.toString() === ""
                readonly property string title: home ? "New tab" : (web.title || web.url.toString())
                function open(url) { web.url = url; web.forceActiveFocus() }
                WebEngineView {
                    id: web
                    anchors.fill: parent
                    visible: !tab.home
                    profile: webProfile
                    url: tab.startUrl
                    settings.fullScreenSupportEnabled: true
                    settings.pluginsEnabled: false
                    settings.javascriptCanOpenWindows: true
                    settings.localContentCanAccessRemoteUrls: false
                    onUrlChanged: if (tab.index === stack.currentIndex && !address.activeFocus) address.text = url.toString()
                    onLoadingChanged: request => {
                        if (request.status === WebEngineLoadingInfo.LoadSucceededStatus)
                            browser.visited(request.url.toString(), web.title)
                    }
                    onNewWindowRequested: request => {
                        const t = win.newTab("", false)
                        request.openIn(t.view)
                    }
                    onFullScreenRequested: request => {
                        request.accept()
                        if (request.toggleOn) win.showFullScreen(); else win.showNormal()
                    }
                    onFeaturePermissionRequested: (origin, feature) => permission.ask(web, origin, feature)
                    onCertificateError: error => error.rejectCertificate()
                    onRenderProcessTerminated: (status, code) => { if (status !== WebEngineView.NormalTerminationStatus) web.reload() }
                }
                StartPage { anchors.fill: parent; visible: tab.home; onOpenUrl: url => tab.open(browser.normalize(url)) }
            }
        }
    }

    // ------------------------------------------------------------ start page
    component StartPage: Item {
        id: sp
        signal openUrl(string url)
        Rectangle { anchors.fill: parent; color: Theme.bgBottom }
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.06) }
                GradientStop { position: 0.6; color: "transparent" }
            }
        }
        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.max(40, parent.height * 0.16); width: Math.min(720, parent.width - 60); spacing: 22
            ApvisMark { anchors.horizontalCenter: parent.horizontalCenter; width: 76; height: 67; glow: 1 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: Theme.label("APVIS BROWSER"); color: Theme.text
                   font.pixelSize: 26; font.weight: Font.Light; font.letterSpacing: 8; leftPadding: 8 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; color: Theme.muted; font.pixelSize: 13
                   text: "Trackers blocked · third-party cookies refused · Ask APVIS about any page" }
            Item {
                width: parent.width; height: 50
                Rectangle { anchors.fill: parent; radius: 14; color: Theme.sheen(0.05)
                            border.width: startField.activeFocus ? 1.5 : 1; border.color: startField.activeFocus ? Theme.accent : Theme.line }
                TextField {
                    id: startField
                    anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18
                    background: null; color: Theme.text; font.pixelSize: 16; verticalAlignment: TextInput.AlignVCenter
                    placeholderText: "Search with DuckDuckGo or type an address"; placeholderTextColor: Theme.muted
                    onAccepted: if (text.trim()) sp.openUrl(text)
                    Accessible.name: "Search or address"
                }
            }
            Text { visible: browser.recent.length > 0; text: Theme.label("RECENT"); color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 11; font.letterSpacing: Theme.caps ? 2 : 0.3 }
            Flow {
                width: parent.width; spacing: 10
                Repeater {
                    model: browser.recent
                    delegate: AbstractButton {
                        id: rc
                        required property var modelData
                        width: (sp.width > 800 ? (Math.min(720, sp.width - 60) - 30) / 4 : (Math.min(720, sp.width - 60) - 10) / 2); height: 64
                        hoverEnabled: true
                        onClicked: sp.openUrl(modelData.url)
                        Accessible.name: modelData.title
                        background: Rectangle { radius: 10; color: rc.hovered ? Theme.raised : Theme.sheen(0.03)
                                                border.width: 1; border.color: rc.hovered ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.5) : Theme.line }
                        contentItem: Column {
                            leftPadding: 12; rightPadding: 12; topPadding: 12; spacing: 4
                            Text { width: rc.width - 24; elide: Text.ElideRight; text: rc.modelData.title; color: Theme.text; font.pixelSize: 13 }
                            Text { width: rc.width - 24; elide: Text.ElideRight; text: rc.modelData.host; color: Theme.muted; font.pixelSize: 11 }
                        }
                    }
                }
            }
            Text { visible: browser.recent.length > 0; text: "Clear history"; color: Theme.muted; font.pixelSize: 11
                   MouseArea { anchors.fill: parent; anchors.margins: -4; cursorShape: Qt.PointingHandCursor; onClicked: browser.clearHistory() } }
        }
        Component.onCompleted: Qt.callLater(() => startField.forceActiveFocus())
    }

    // ------------------------------------------------------------ Ask APVIS panel
    Rectangle {
        id: askPanel
        property bool open: false
        readonly property var a: browser.answer || ({})
        anchors.top: toolbar.bottom; anchors.bottom: parent.bottom; anchors.right: parent.right
        width: open ? Math.min(440, win.width * 0.38) : 0
        Behavior on width { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
        clip: true
        color: Theme.panel
        Rectangle { width: 1; height: parent.height; color: Theme.line }
        Column {
            x: 18; y: 16; width: askPanel.width - 36; spacing: 12
            visible: askPanel.width > 200
            Row {
                spacing: 10
                Glyph { width: 20; height: 20; kind: "brain"; stroke: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                Text { text: Theme.label("ASK APVIS"); color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 12; font.letterSpacing: Theme.caps ? 2 : 0.3; font.bold: true
                       anchors.verticalCenter: parent.verticalCenter }
            }
            Text { width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 12
                   text: "About: " + (current ? current.title : "") }
            Flow {
                width: parent.width; spacing: 6
                Repeater {
                    model: ["Summarise this page", "What are the key facts?", "Explain it simply", "Is this trustworthy?"]
                    delegate: AbstractButton {
                        required property string modelData
                        height: 28; width: chip.implicitWidth + 20
                        onClicked: win.askPage(modelData)
                        background: Rectangle { radius: 14; color: parent.hovered ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.15) : Theme.sheen(0.04)
                                                border.width: 1; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.35) }
                        contentItem: Text { id: chip; text: parent.modelData; color: Theme.text; font.pixelSize: 12
                                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    }
                }
            }
            Item {
                width: parent.width; height: 40
                Rectangle { anchors.fill: parent; radius: 10; color: Theme.sheen(0.05); border.width: askField.activeFocus ? 1.5 : 1
                            border.color: askField.activeFocus ? Theme.accent : Theme.line }
                TextField {
                    id: askField
                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                    background: null; color: Theme.text; font.pixelSize: 13; verticalAlignment: TextInput.AlignVCenter
                    placeholderText: "Ask anything about this page…"; placeholderTextColor: Theme.muted
                    onAccepted: { win.askPage(text); text = "" }
                    Accessible.name: "Question about this page"
                }
            }
            Text { visible: !!askPanel.a.question; width: parent.width; wrapMode: Text.WordWrap; text: askPanel.a.question || ""
                   color: Theme.muted; font.pixelSize: 12; font.italic: true }
        }
        Flickable {
            x: 18; width: askPanel.width - 36
            y: 260; height: askPanel.height - y - 16
            contentHeight: answerText.height; clip: true
            visible: askPanel.width > 200
            ScrollBar.vertical: HudScrollBar {}
            Text {
                id: answerText
                width: parent.width - 8; wrapMode: Text.WordWrap; textFormat: Text.MarkdownText
                color: askPanel.a.state === "error" ? Theme.attention : Theme.text; font.pixelSize: 14; lineHeight: 1.25
                text: askPanel.a.state === "thinking" ? "Reading the page…" : (askPanel.a.text || "") +
                      (askPanel.a.meta ? "\n\n*" + askPanel.a.meta + "*" : "")
            }
        }
    }

    // ------------------------------------------------------------ permission prompt
    Rectangle {
        id: permission
        property var view: null
        property url origin
        property int feature: -1
        function ask(v, o, f) { view = v; origin = o; feature = f; visible = true }
        function answer(yes) { if (view) view.grantFeaturePermission(origin, feature, yes); visible = false }
        readonly property string what: ({ [WebEngineView.Geolocation]: "know your location", [WebEngineView.MediaAudioCapture]: "use your microphone",
                                          [WebEngineView.MediaVideoCapture]: "use your camera", [WebEngineView.MediaAudioVideoCapture]: "use your camera and microphone",
                                          [WebEngineView.Notifications]: "show notifications", [WebEngineView.DesktopVideoCapture]: "share your screen",
                                          [WebEngineView.DesktopAudioVideoCapture]: "share your screen and audio" })[feature] || "use a device feature"
        visible: false
        anchors.horizontalCenter: stack.horizontalCenter; y: toolbar.y + toolbar.height + 10
        width: Math.min(620, stack.width - 40); height: 58; radius: 12; z: 5
        color: Theme.panel; border.width: 1; border.color: Theme.attention
        Text { x: 16; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 260; elide: Text.ElideRight
               text: permission.origin.toString().replace(/^https?:\/\//, "") + " wants to " + permission.what; color: Theme.text; font.pixelSize: 13 }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; spacing: 8
            HudButton { width: 100; implicitHeight: 34; caption: "Block"; onClicked: permission.answer(false) }
            HudButton { width: 100; implicitHeight: 34; caption: "Allow"; tone: "primary"; onClicked: permission.answer(true) }
        }
    }

    // ------------------------------------------------------------ downloads
    Rectangle {
        id: downloads
        property bool shown: false
        property int active: 0
        property var items: []                   // WebEngineDownloadRequest objects, newest first
        function add(d) {
            items = [d].concat(items).slice(0, 8)
            shown = true
            active += 1
            d.isFinishedChanged.connect(() => { active = Math.max(0, active - 1) })
        }
        visible: shown && items.length > 0
        anchors.right: parent.right; anchors.rightMargin: askPanel.width + 12; y: toolbar.y + toolbar.height + 10; z: 5
        width: 380; height: Math.min(300, dlCol.height + 24); radius: 12
        color: Theme.panel; border.width: 1; border.color: Theme.line
        Column {
            id: dlCol
            x: 14; y: 12; width: parent.width - 28; spacing: 10
            Text { text: Theme.label("DOWNLOADS  ·  ") + browser.downloadPath; color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: 1.2
                   width: parent.width; elide: Text.ElideMiddle }
            Repeater {
                model: downloads.items
                delegate: Column {
                    required property var modelData
                    width: dlCol.width; spacing: 4
                    readonly property var d: modelData
                    Text { width: parent.width; elide: Text.ElideMiddle; text: parent.d ? parent.d.downloadFileName : ""; color: Theme.text; font.pixelSize: 13 }
                    Rectangle {
                        width: parent.width; height: 4; radius: 2; color: Theme.sheen(0.08)
                        Rectangle { height: parent.height; radius: 2; color: Theme.accent
                                    width: parent.width * (parent.parent.d && parent.parent.d.totalBytes > 0 ? parent.parent.d.receivedBytes / parent.parent.d.totalBytes : 0) }
                    }
                    Text { color: Theme.muted; font.pixelSize: 11
                           text: !parent.d ? "" : parent.d.isFinished ? (parent.d.state === WebEngineDownloadRequest.DownloadCompleted ? "Done" : "Stopped")
                                 : Math.round(parent.d.receivedBytes / 1048576) + " MB" + (parent.d.totalBytes > 0 ? " of " + Math.round(parent.d.totalBytes / 1048576) + " MB" : "") }
                }
            }
        }
    }
}
