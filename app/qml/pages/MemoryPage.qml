import QtQuick
import QtQuick.Controls
import "../theme"

// Memory: what APVIS remembers about the owner, and what waits for review.
// Nothing is kept without a Save; every memory is a plain Markdown file in the
// vault, can be opened in an editor, and "Forget" moves it to the Trash.
Item {
    id: page
    readonly property var inbox: shell.inbox || []
    readonly property var memories: shell.notes || []
    readonly property var sessions: shell.episodes || []
    readonly property bool sessionsOn: !!((shell.settings || {}).episodes || {}).enabled
    property bool armedForgetAll: false
    property string kindFilter: ""
    property string textFilter: ""
    // V3 M2: a pause in typing searches the whole vault (by meaning too, when it is on); until the
    // answer arrives, the words typed filter what is already shown.
    readonly property var memInfo: (shell.settings && shell.settings.memory) || ({})
    readonly property var aiQueue: (shell.settings && shell.settings.aiQueue) || ({})
    readonly property var msearch: (shell.settings && shell.settings.memorySearch) || ({})
    readonly property bool searched: textFilter.length >= 3 && msearch.query === textFilter && !msearch.busy && !msearch.error
    readonly property var shown: searched
        ? (msearch.results || []).filter(m => !kindFilter || m.kind === kindFilter)
        : memories.filter(m =>
            (!kindFilter || m.kind === kindFilter) &&
            (!textFilter || (m.title + " " + (m.excerpt || "") + " " + (m.tags || []).join(" ")).toLowerCase().indexOf(textFilter.toLowerCase()) >= 0))
    Timer { id: searchDelay; interval: 600; onTriggered: if (page.textFilter.length >= 3) shell.searchMemory(page.textFilter) }
    function queueWords(q) {
        if (!q.state || q.state === "idle") return Theme.label("AI QUEUE IDLE")
        if (q.state === "live") return Theme.label("ANSWERING YOU")
        if (q.state === "plan") return q.running === "warm-up" ? Theme.label("LOADING THE MODEL") : Theme.label("RUNNING A PLAN STEP")
        if (q.state === "background") return Theme.label("INDEXING WHILE IDLE")
        return Theme.label("WAITING")
    }
    readonly property bool wide: width >= 980
    property string armedForget: ""
    signal suggest(string text)
    Timer { id: disarm; interval: 4000; onTriggered: { page.armedForget = ""; page.armedForgetAll = false } }
    function focusFirst() { filterField.forceActiveFocus() }
    function kindWord(k) { return k === "decision" ? Theme.label("DECISION") : k === "research" ? Theme.label("RESEARCH") : Theme.label("NOTE") }
    function kindColour(k) { return k === "decision" ? Theme.warm : k === "research" ? Theme.info : Theme.accent }
    function kindCount(k) { return memories.filter(m => m.kind === k).length }

    property real reveal: 1
    onVisibleChanged: if (visible) entry.restart()
    NumberAnimation { id: entry; target: page; property: "reveal"; from: 0; to: 1; duration: 800; easing.type: Easing.OutCubic }

    PageHeader {
        id: header
        width: parent.width
        code: "04"; title: "MEMORY"; reveal: page.reveal
        subtitle: "What APVIS remembers about you. It only keeps what you Save. Each memory is a plain Markdown file in " + shell.vaultPath + "."
        HudButton { width: 170; glyph: "files"; caption: "Open vault folder"; onClicked: shell.openVault() }
    }

    Row {
        id: counts
        anchors.top: header.bottom; anchors.topMargin: 16
        width: parent.width; spacing: 12
        readonly property real tileWidth: (width - 4 * spacing) / 5
        StatTile { width: counts.tileWidth; order: 0; reveal: page.reveal; label: "REMEMBERED"; glyph: "memory"
                   value: String(page.memories.length); live: page.memories.length > 0 }
        StatTile { width: counts.tileWidth; order: 1; reveal: page.reveal; label: "NOTES"; glyph: "notes"
                   value: String(page.kindCount("note")); live: page.kindCount("note") > 0
                   fraction: page.memories.length ? page.kindCount("note") / page.memories.length : 0 }
        StatTile { width: counts.tileWidth; order: 2; reveal: page.reveal; label: "DECISIONS"; glyph: "check"; tint: Theme.warm
                   value: String(page.kindCount("decision")); live: page.kindCount("decision") > 0
                   fraction: page.memories.length ? page.kindCount("decision") / page.memories.length : 0 }
        StatTile { width: counts.tileWidth; order: 3; reveal: page.reveal; label: "RESEARCH"; glyph: "search"; tint: Theme.info
                   value: String(page.kindCount("research")); live: page.kindCount("research") > 0
                   fraction: page.memories.length ? page.kindCount("research") / page.memories.length : 0 }
        StatTile { width: counts.tileWidth; order: 4; reveal: page.reveal; label: "WAITING FOR REVIEW"; glyph: "ask"; tint: Theme.attention
                   value: String(page.inbox.length); live: page.inbox.length > 0; sub: page.inbox.length ? "review below" : "" }
    }

    // ---- review column
    Flickable {
        id: reviewCol
        anchors.top: counts.bottom; anchors.topMargin: 16
        width: page.wide ? Math.min(420, parent.width * 0.34) : parent.width
        height: page.wide ? parent.height - y : Math.min(300, reviewStack.height)
        visible: page.wide || page.inbox.length > 0
        contentHeight: reviewStack.height
        clip: true; boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: HudScrollBar {}
        Column {
            id: reviewStack
            width: reviewCol.width - 10; spacing: 14
            HudPanel {
                width: parent.width; reveal: page.reveal; order: 2
                title: "WAITING FOR YOUR REVIEW"; glyph: "ask"
                tint: page.inbox.length ? Theme.attention : Theme.accent
                highlighted: page.inbox.length > 0
                meta: page.inbox.length ? page.inbox.length + " NEW" : "CLEAR"
                metaColour: page.inbox.length ? Theme.attention : Theme.muted
                Text { visible: page.inbox.length === 0; width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 12
                       text: "Nothing waiting. When you ask APVIS to remember something, it appears here first and is only kept if you Save it." }
                Repeater {
                    model: page.inbox
                    delegate: Item {
                        required property var modelData
                        width: parent.width; height: reviewBody.height + 62
                        Chamfer { anchors.fill: parent; cut: 10; fill: Theme.bgBottom; fillOpacity: 0.6; stroke: Qt.rgba(Theme.attention.r, Theme.attention.g, Theme.attention.b, 0.6) }
                        Rectangle { x: 0; y: 10; width: 2.5; height: parent.height - 20; color: Theme.attention }
                        Column {
                            id: reviewBody
                            x: 14; y: 12; width: parent.width - 28; spacing: 4
                            Text { text: page.kindWord(modelData.kind); color: Theme.attention; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 2 : 0.3 }
                            Text { width: parent.width; text: modelData.text; color: Theme.text; font.pixelSize: 14; wrapMode: Text.WordWrap }
                            Text { width: parent.width; visible: text.length > 0; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.WordWrap
                                   text: (modelData.reason ? "Why: " + modelData.reason + "   " : "") +
                                         (modelData.similar.length ? "Similar to: " + modelData.similar.join(", ") : "") }
                        }
                        Row {
                            anchors.bottom: parent.bottom; anchors.bottomMargin: 10; x: 14; spacing: 8
                            HudButton { width: 90; implicitHeight: 32; caption: "Save"; glyph: "check"; tone: "primary"; onClicked: shell.acceptMemory(modelData.id) }
                            HudButton { width: 110; implicitHeight: 32; caption: "Don't save"; onClicked: shell.rejectMemory(modelData.id) }
                        }
                    }
                }
            }
            HudPanel {
                visible: page.wide
                width: parent.width; reveal: page.reveal; order: 3
                title: "HOW MEMORY WORKS"; glyph: "brain"
                Repeater {
                    model: [["ask", "Say it", "“remember that …” or “we decided … because …” in the Ask bar."],
                            ["check", "You review it", "It waits above until you press Save. Nothing is kept on its own."],
                            ["notes", "It's a file you own", "Plain Markdown in your vault. Open it, edit it, or Forget it (goes to the Trash)."],
                            ["brain", "Ask uses it", "Relevant memories are given to the local AI when you ask, and nothing leaves this computer."]]
                    delegate: Row {
                        required property var modelData
                        width: parent.width; spacing: 12
                        Rectangle { width: 28; height: 28; radius: 14; color: Theme.bgBottom
                                    border.width: 1; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.55)
                                    Glyph { anchors.centerIn: parent; width: 13; height: 13; kind: modelData[0]; stroke: Theme.accent } }
                        Column {
                            width: parent.width - 40; spacing: 2
                            Text { text: Theme.upper(modelData[1]); color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 11; font.letterSpacing: Theme.caps ? 1.4 : 0.3 }
                            Text { width: parent.width; text: modelData[2]; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.WordWrap }
                        }
                    }
                }
            }
        }
    }

    // ---- remembered
    Item {
        id: memArea
        anchors.top: page.wide ? counts.bottom : reviewCol.bottom
        anchors.topMargin: 16; anchors.bottom: parent.bottom
        x: page.wide ? reviewCol.width + 12 : 0
        width: parent.width - x
        opacity: page.reveal
        transform: Translate { x: (1 - page.reveal) * 20 }
        Row {
            id: filters
            width: parent.width; spacing: 10
            TextField {
                id: filterField
                width: Math.max(160, parent.width - kinds.width - 10); height: 34
                placeholderText: "Find in memory…"; verticalAlignment: TextInput.AlignVCenter
                leftPadding: 34
                color: Theme.text; placeholderTextColor: Theme.muted; selectByMouse: true; font.pixelSize: 13
                Accessible.name: "Find in memory"
                background: Item {
                    Chamfer { anchors.fill: parent; cut: 8; fill: Theme.bgBottom; fillOpacity: 0.6
                              stroke: filterField.activeFocus ? Theme.accent : Theme.line; strokeWidth: filterField.activeFocus ? 1.5 : 1 }
                    Glyph { x: 11; anchors.verticalCenter: parent.verticalCenter; width: 14; height: 14; kind: "search"
                            stroke: filterField.activeFocus ? Theme.accent : Theme.muted }
                }
                onTextChanged: { page.textFilter = text.trim(); searchDelay.restart() }
                onAccepted: if (page.textFilter.length) shell.searchMemory(page.textFilter)
            }
            Segmented {
                id: kinds
                options: ["", "note", "decision", "research", "sessions"]
                value: page.kindFilter
                label: v => v === "" ? "All" : v === "note" ? "Notes" : v === "decision" ? "Decisions" : v === "research" ? "Research" : "Sessions"
                onPicked: v => page.kindFilter = v
            }
        }
        Text {
            id: countLine
            anchors.top: filters.bottom; anchors.topMargin: 14
            text: page.kindFilter === "sessions" ? Theme.label("SESSIONS  ·  ") + sessionsView.shownSessions.length :
                  (page.searched ?(page.msearch.mode === "hybrid" ? "BEST MATCHES BY MEANING" : "BEST MATCHES BY WORDS") + "  ·  " + page.shown.length
                                 : "REMEMBERED  ·  " + page.shown.length + (page.shown.length !== page.memories.length ? " OF " + page.memories.length : ""))
            color: page.searched ? Theme.accent : Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: 2
        }
        Text {
            id: indexLine
            anchors.top: filters.bottom; anchors.topMargin: 14; anchors.right: parent.right
            width: Math.max(0, parent.width - countLine.implicitWidth - 24); horizontalAlignment: Text.AlignRight; elide: Text.ElideLeft
            color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: 1.5
            text: (page.memInfo.enabled
                   ? "MEANING SEARCH ON" + (page.memInfo.notes ? "  ·  " + page.memInfo.notes + " NOTES INDEXED" : "")
                     + (page.memInfo.state === "paused" ? " (PAUSED FOR YOU)" : "")
                   : "SEARCH BY WORDS  ·  MEANING SEARCH IN SETTINGS > LOCAL AI")
                  + "  ·  " + page.queueWords(page.aiQueue)
        }
        // ---- V3 M4: sessions (episodes)
        Item {
            id: sessionsView
            visible: page.kindFilter === "sessions"
            anchors.top: countLine.bottom; anchors.topMargin: 10; anchors.bottom: parent.bottom
            width: parent.width
            readonly property var shownSessions: page.sessions.filter(e => !page.textFilter ||
                (e.summary + " " + (e.questions || []).join(" ")).toLowerCase().indexOf(page.textFilter.toLowerCase()) >= 0)
            Row {
                id: sessionsBar
                width: parent.width; spacing: 10
                Text { width: parent.width - forgetAll.width - 10; anchors.verticalCenter: parent.verticalCenter
                       wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 12
                       text: page.sessionsOn ? "One line per Ask session, written on this computer while it was idle. Each is deleted after 30 days."
                                             : "Session memory is off (Settings > Local AI). " + (page.sessions.length ? "These saved sessions stay until they expire or you forget them." : "Nothing is remembered.") }
                HudButton {
                    id: forgetAll
                    width: 150; implicitHeight: 30; visible: page.sessions.length > 0
                    tone: page.armedForgetAll ? "warning" : "normal"
                    caption: page.armedForgetAll ? "Press again" : "Forget all"
                    onClicked: { if (page.armedForgetAll) { page.armedForgetAll = false; shell.forgetAllEpisodes() } else { page.armedForgetAll = true; disarm.restart() } }
                }
            }
            ListView {
                anchors.top: sessionsBar.bottom; anchors.topMargin: 12; anchors.bottom: parent.bottom
                width: parent.width; clip: true; spacing: 8
                model: sessionsView.shownSessions
                ScrollBar.vertical: HudScrollBar {}
                delegate: Item {
                    required property var modelData
                    width: ListView.view.width - 12; height: sessionText.height + 44
                    Chamfer { anchors.fill: parent; cut: 10; fill: Theme.raised; fillOpacity: 0.7; stroke: Theme.line }
                    Rectangle { x: 0; y: 10; width: 2.5; height: parent.height - 20; color: Theme.info }
                    Column {
                        x: 16; y: 10; width: parent.width - 140; spacing: 4
                        Text { text: Qt.formatDateTime(new Date(modelData.ended), "ddd d MMM, HH:mm") + "  ·  " + modelData.turns + (modelData.turns === 1 ? " question" : " questions")
                               color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10 }
                        Text { id: sessionText; width: parent.width; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 14; text: modelData.summary }
                    }
                    HudButton {
                        anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                        width: 100; implicitHeight: 28
                        tone: page.armedForget === modelData.episode_id ? "warning" : "normal"
                        caption: page.armedForget === modelData.episode_id ? "Press again" : "Forget"
                        onClicked: { if (page.armedForget === modelData.episode_id) { page.armedForget = ""; shell.forgetEpisode(modelData.episode_id) }
                                     else { page.armedForget = modelData.episode_id; disarm.restart() } }
                    }
                }
            }
        }
        EmptyState {
            visible: page.memories.length === 0 && page.kindFilter !== "sessions"
            anchors.top: countLine.bottom; anchors.topMargin: Math.max(10, (memArea.height - countLine.y - height) / 2 - 40)
            width: parent.width
            glyph: "memory"; title: "Nothing remembered yet"
            hint: "Tell APVIS something worth keeping. It shows up for your review first, then lives here as a note you own."
            suggestions: ["remember that I like short answers", "we decided on emerald because it looks best"]
            onSuggested: text => page.suggest(text)
        }
        Text {
            anchors.top: countLine.bottom; anchors.topMargin: 12; visible: page.memories.length > 0 && page.shown.length === 0 && page.kindFilter !== "sessions"
            width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 12
            text: "Nothing matches."
        }
        GridView {
            id: memGrid
            visible: page.kindFilter !== "sessions"
            anchors.top: countLine.bottom; anchors.topMargin: 10; anchors.bottom: parent.bottom
            width: parent.width; clip: true
            readonly property int columns: width > 1100 ? 3 : width > 700 ? 2 : 1
            cellWidth: width / columns; cellHeight: 150
            model: page.shown
            ScrollBar.vertical: HudScrollBar {}
            delegate: Item {
                id: card
                required property var modelData
                required property int index
                readonly property color tone: page.kindColour(modelData.kind)
                width: memGrid.cellWidth; height: memGrid.cellHeight
                // Cards cascade in when the page opens.
                readonly property real local: Math.max(0, Math.min(1, page.reveal * 2 - index * 0.08))
                opacity: local
                transform: Translate { y: (1 - card.local) * 14 }
                Chamfer { x: 0; y: 0; width: parent.width - 12; height: parent.height - 12; cut: 12
                          fill: Theme.raised; fillOpacity: 0.8; fill2: Theme.bgBottom; fill2Opacity: 0.75
                          stroke: cardMouse.containsMouse ? card.tone : Theme.line
                          edgeGlow: cardMouse.containsMouse; glowColour: card.tone }
                MouseArea { id: cardMouse; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                Rectangle { x: 0; y: 12; width: 2.5; height: parent.height - 36; color: card.tone }
                Column {
                    x: 16; y: 13; width: parent.width - 40; spacing: 4
                    Row {
                        spacing: 8
                        Rectangle {
                            width: kindText.implicitWidth + 12; height: 17; radius: 3
                            color: Qt.rgba(card.tone.r, card.tone.g, card.tone.b, 0.12); border.width: 1
                            border.color: Qt.rgba(card.tone.r, card.tone.g, card.tone.b, 0.5)
                            Text { id: kindText; anchors.centerIn: parent; text: page.kindWord(card.modelData.kind); color: card.tone
                                   font.family: Theme.monoFont; font.pixelSize: 9; font.letterSpacing: Theme.caps ? 1.5 : 0.3 }
                        }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: card.modelData.updated ? card.modelData.updated.slice(0, 10) : ""
                               color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10 }
                    }
                    Text { width: parent.width; text: card.modelData.title; color: Theme.text; font.pixelSize: 15; elide: Text.ElideRight }
                    Text { width: parent.width; text: card.modelData.excerpt || " "; color: Theme.muted; font.pixelSize: 11
                           wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight }
                }
                Row {
                    x: 16; anchors.bottom: parent.bottom; anchors.bottomMargin: 22; spacing: 8
                    HudButton { width: 76; implicitHeight: 28; caption: "Open"; onClicked: shell.openNote(card.modelData.path) }
                    HudButton {
                        width: 100; implicitHeight: 28
                        tone: page.armedForget === card.modelData.path ? "warning" : "normal"
                        caption: page.armedForget === card.modelData.path ? "Press again" : "Forget"
                        Accessible.name: "Forget " + card.modelData.title
                        onClicked: {
                            if (page.armedForget === card.modelData.path) { page.armedForget = ""; shell.forgetMemory(card.modelData.path) }
                            else { page.armedForget = card.modelData.path; disarm.restart() }
                        }
                    }
                    Text { anchors.verticalCenter: parent.verticalCenter; visible: (card.modelData.tags || []).length > 0
                           text: (card.modelData.tags || []).slice(0, 3).map(t => "#" + t).join("  "); color: Theme.muted
                           font.family: Theme.monoFont; font.pixelSize: 10; elide: Text.ElideRight; width: Math.max(0, card.width - 240) }
                }
            }
        }
    }
}
