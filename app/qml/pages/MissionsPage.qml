import QtQuick
import QtQuick.Controls
import "../theme"

// Mission Control: everything APVIS was asked to do, as a timeline. Changes
// wait for approval; every result is checked afterwards; every run is logged.
Item {
    id: page
    readonly property var missions: shell.missions || []
    readonly property bool wide: width >= 1100
    readonly property bool still: !!(shell.render || {}).reducedMotion || !!(shell.render || {}).lite
    signal suggest(string text)
    function statusText(status) {
        return status === "approval_required" ? "Waiting for you" : status === "completed" ? "Done" :
               status === "failed" ? "Did not complete" : status === "cancelled" ? "Cancelled" :
               status === "running" ? "Running" : status
    }
    function statusColour(status) {
        return status === "approval_required" || status === "failed" ? Theme.attention :
               status === "completed" ? Theme.accent : Theme.muted
    }
    function statusGlyph(status) { return status === "completed" ? "check" : status === "approval_required" ? "mission" : "activity" }
    function count(status) { return missions.filter(m => m.status === status).length }

    property real reveal: 1
    onVisibleChanged: if (visible) entry.restart()
    NumberAnimation { id: entry; target: page; property: "reveal"; from: 0; to: 1; duration: 800; easing.type: Easing.OutCubic }

    PageHeader {
        id: header
        width: parent.width
        code: "02"; title: "MISSION CONTROL"; reveal: page.reveal
        subtitle: "Everything APVIS was asked to do. Changes wait for your approval, every result is checked afterwards, and every run is logged."
        HudButton {
            width: 150; caption: "Clear finished"; glyph: "check"
            visible: page.missions.some(m => m.status !== "approval_required" && m.status !== "running")
            onClicked: shell.archiveMissions()
        }
    }

    // Counts.
    Row {
        id: counts
        anchors.top: header.bottom; anchors.topMargin: 16
        width: parent.width; spacing: 12
        readonly property real tileWidth: (width - 3 * spacing) / 4
        Repeater {
            model: [["approval_required", "WAITING FOR YOU", "mission", "needs approval"], ["completed", "DONE", "check", "checked"],
                    ["failed", "DID NOT COMPLETE", "activity", "see why"], ["cancelled", "CANCELLED", "restart", ""]]
            delegate: StatTile {
                required property var modelData
                required property int index
                readonly property int n: page.count(modelData[0])
                width: counts.tileWidth; order: index; reveal: page.reveal
                value: String(n); label: modelData[1]; glyph: modelData[2]
                sub: n > 0 ? modelData[3] : ""
                live: n > 0
                tint: modelData[0] === "completed" ? Theme.accent : modelData[0] === "cancelled" ? Theme.muted : Theme.attention
                fraction: page.missions.length ? n / page.missions.length : 0
            }
        }
    }

    // ---- how missions work (right column on wide screens)
    HudPanel {
        id: how
        visible: page.wide
        anchors.top: counts.bottom; anchors.topMargin: 16; anchors.right: parent.right
        width: 330; reveal: page.reveal; order: 3
        title: "HOW A MISSION RUNS"; glyph: "mission"
        Item {
            id: steps
            width: parent.width; height: stepCol.height
            readonly property var model: [
                ["ask", "You ask", "Type it in the Ask bar, like “open my Downloads”."],
                ["brain", "APVIS plans it", "One exact action, shown to you in plain words."],
                ["check", "You approve", "Nothing on the computer changes until you press Approve."],
                ["activity", "It runs", "Only that action. Nothing else is touched."],
                ["notes", "Checked and logged", "The result is read back, and every run is kept here."]]
            // Spine + a light travelling down it.
            Rectangle { x: 15; y: 16; width: 1; height: stepCol.height - 40; color: Theme.line }
            Rectangle {
                id: runner
                x: 12; width: 7; height: 7; radius: 3.5; color: Theme.accent
                visible: !page.still
                NumberAnimation on y { from: 16; to: stepCol.height - 30; duration: 4200; loops: Animation.Infinite; running: page.visible && !page.still
                                       easing.type: Easing.InOutSine }
                Rectangle { anchors.centerIn: parent; width: 18; height: 18; radius: 9; color: Theme.accent; opacity: 0.2 }
            }
            Column {
                id: stepCol
                width: parent.width; spacing: 14
                Repeater {
                    model: steps.model
                    delegate: Item {
                        required property var modelData
                        required property int index
                        width: stepCol.width; height: Math.max(32, stepText.height)
                        Rectangle { width: 31; height: 31; radius: 15.5; color: Theme.bgBottom
                                    border.width: 1; border.color: index === 2 ? Theme.attention : Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.6)
                                    Glyph { anchors.centerIn: parent; width: 14; height: 14; kind: modelData[0]; stroke: index === 2 ? Theme.attention : Theme.accent } }
                        Column {
                            id: stepText
                            x: 44; width: parent.width - 44; spacing: 2
                            Text { text: (index + 1) + "  " + Theme.upper(modelData[1]); color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 11; font.letterSpacing: Theme.caps ? 1.4 : 0.3 }
                            Text { width: parent.width; text: modelData[2]; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.WordWrap }
                        }
                    }
                }
            }
        }
    }

    // ---- the timeline
    Item {
        id: listArea
        anchors.top: counts.bottom; anchors.topMargin: 16; anchors.bottom: parent.bottom
        width: page.wide ? parent.width - how.width - 18 : parent.width

        EmptyState {
            visible: page.missions.length === 0
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.max(10, (parent.height - height) / 2 - 20)
            width: parent.width
            opacity: page.reveal
            glyph: "mission"; title: "No missions yet"
            hint: "Ask APVIS to do something on this computer. It shows you the exact action first and waits for your Approve."
            suggestions: ["open my Downloads", "set the volume to 40%"]
            onSuggested: text => page.suggest(text)
        }

        ListView {
            id: list
            anchors.fill: parent
            clip: true; spacing: 12
            model: page.missions
            ScrollBar.vertical: HudScrollBar {}
            add: Transition { NumberAnimation { properties: "opacity"; from: 0; to: 1; duration: 260 } }
            remove: Transition { NumberAnimation { properties: "opacity"; to: 0; duration: 200 } }
            displaced: Transition { NumberAnimation { properties: "y"; duration: 240; easing.type: Easing.OutCubic } }
            delegate: Item {
                id: card
                required property var modelData
                required property int index
                readonly property bool waiting: modelData.status === "approval_required"
                readonly property color tone: page.statusColour(modelData.status)
                width: ListView.view.width - 12; height: body.height + 30
                readonly property real local: Math.max(0, Math.min(1, page.reveal * 2 - index * 0.1))
                opacity: local
                transform: Translate { x: (1 - card.local) * 20 }
                // Timeline: a node per mission, joined by a line.
                Rectangle { x: 16; y: 20; width: 1; height: parent.height + 12; color: Theme.line; visible: card.index < list.count - 1 }
                Item {
                    x: 3; y: 8; width: 27; height: 27
                    Rectangle { anchors.centerIn: parent; width: 27; height: 27; radius: 13.5; color: card.tone; opacity: card.waiting ? 0.18 : 0.08 }
                    Rectangle {
                        anchors.centerIn: parent; width: 21; height: 21; radius: 10.5
                        color: Theme.bgBottom; border.width: 1.5; border.color: card.tone
                        Glyph { anchors.centerIn: parent; width: 11; height: 11; kind: page.statusGlyph(card.modelData.status); stroke: card.tone }
                    }
                    SequentialAnimation on scale {
                        running: card.waiting && page.visible && !page.still; loops: Animation.Infinite
                        NumberAnimation { to: 1.2; duration: 700; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 1.0; duration: 700; easing.type: Easing.InOutSine }
                    }
                }
                Item {
                    x: 42; width: parent.width - 42; height: parent.height
                    Chamfer { anchors.fill: parent; cut: 12; fill: Theme.raised; fillOpacity: 0.8; fill2: Theme.bgBottom; fill2Opacity: 0.75
                              stroke: card.waiting ? Theme.attention : Theme.line; edgeGlow: card.waiting; glowColour: Theme.attention
                              brackets: card.waiting; bracketColour: Theme.attention }
                    Rectangle { x: 0; y: 12; width: 2.5; height: parent.height - 24; color: card.tone }
                    Column {
                        id: body
                        x: 18; y: 15; width: parent.width - 36 - (actions.visible ? actions.width + 12 : 0); spacing: 5
                        Row {
                            spacing: 10
                            Rectangle {
                                width: statusWord.implicitWidth + 14; height: 18; radius: 3
                                color: Qt.rgba(card.tone.r, card.tone.g, card.tone.b, 0.12); border.width: 1
                                border.color: Qt.rgba(card.tone.r, card.tone.g, card.tone.b, 0.55)
                                Text { id: statusWord; anchors.centerIn: parent; text: page.statusText(card.modelData.status).toUpperCase()
                                       color: card.tone; font.family: Theme.monoFont; font.pixelSize: 9; font.letterSpacing: Theme.caps ? 1.6 : 0.3 }
                            }
                            Text { visible: !!card.modelData.verified; anchors.verticalCenter: parent.verticalCenter
                                   text: "✓ RESULT CHECKED"; color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 9; font.letterSpacing: Theme.caps ? 1.4 : 0.3 }
                        }
                        Text { width: parent.width; text: card.modelData.preview; color: Theme.text; font.pixelSize: 16; wrapMode: Text.WordWrap }
                        Text { width: parent.width; visible: text.length > 0; text: card.modelData.message || card.modelData.error || ""
                               color: card.modelData.status === "failed" ? Theme.attention : Theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap }
                        Text { width: parent.width; text: "You asked: “" + card.modelData.asked + "”  ·  " + card.modelData.updatedAt.replace("T", " ").replace("Z", " UTC")
                               color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10; elide: Text.ElideRight }
                    }
                    Row {
                        id: actions
                        visible: card.waiting
                        anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter
                        spacing: 8
                        HudButton { width: 110; caption: "Approve"; glyph: "check"; tone: "primary"; onClicked: shell.approveMission(card.modelData.id, card.modelData.token) }
                        HudButton { width: 92; caption: "Cancel"; onClicked: shell.cancelMission(card.modelData.id) }
                    }
                }
            }
        }
    }
}
