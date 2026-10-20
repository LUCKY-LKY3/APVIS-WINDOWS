import QtQuick
import "../theme"

// ACTIVE TASK (owner concept): the real thing APVIS is doing right now, with
// its real steps — installing, updating, downloading a model, a mission that
// waits for approval, or an answer being written. Otherwise: all quiet.
GlassCard {
    id: card
    title: "ACTIVE TASK"
    signal go(string key)
    readonly property var s: shell.settings || ({})
    readonly property var u: shell.updates || ({})
    readonly property var inst: shell.installer || ({})
    readonly property var ask: shell.ask || ({ state: "closed" })
    readonly property var waiting: (shell.missions || []).filter(m => m.status === "approval_required" || m.status === "running")
    readonly property var task: {
        // Health guard: a real problem on this computer comes first.
        const alerts = (shell.system || {}).health || []
        if (alerts.length) {
            const a = alerts[0]
            return { title: a.title, pct: -2, page: a.action, alert: true, level: a.level, actionLabel: a.action_label,
                     steps: alerts.map(x => [x.detail, false]) }
        }
        if (inst.state === "installing")
            return { title: "Installing APVIS OS", pct: inst.pct || 0, page: "install", detail: inst.message || "",
                     steps: [["Prepare the disk", (inst.pct || 0) > 10], ["Copy the system", (inst.pct || 0) > 70], ["Set up start-up", (inst.pct || 0) > 90], ["Check the result", false]] }
        const ai = (shell.system || {}).aiSetup || {}
        if (ai.state === "running" || ai.state === "waiting" || ai.state === "failed")
            return { title: ai.state === "running" ? "Setting up local AI" : ai.message || "Local AI setup", pct: ai.state === "running" ? (ai.pct || 0) : ai.state === "failed" ? 0 : -1,
                     page: "settings:ai", detail: ai.message || "",
                     steps: (ai.steps || []).map((label, i) => [label, i < (ai.step || 0)]) }
        if (u.state === "installing")
            return { title: "Installing update " + (u.latest || ""), pct: -1, page: "settings",
                     steps: [["Download", true], ["Check the signature", false], ["Stage it", false], ["Restart Home", false]] }
        if (s.pulling)
            return { title: "Downloading " + s.pulling, pct: s.pullPct || 0, page: "settings", detail: s.pullMessage || "",
                     steps: [["Connect to Ollama", true], ["Download the model", (s.pullPct || 0) >= 100], ["Check it", false], ["Ready for Ask", false]] }
        if (waiting.length) {
            const m = waiting[0], running = m.status === "running"
            return { title: running ? "Running: " + m.preview : "Waiting for you: " + m.preview, pct: running ? 75 : 50, page: "missions",
                     steps: [["You asked", true], ["Planned one action", true], ["Your approval", running], ["Run and check", false]] }
        }
        if (ask.state === "thinking" || ask.state === "streaming")
            return { title: "Answering: " + (ask.question || ""), pct: -1, page: "",
                     steps: [["Question received", true], ["Model chosen", ask.state === "streaming"], ["Writing the answer", false]] }
        if (u.state === "checking")
            return { title: "Checking for updates", pct: -1, page: "settings", steps: [] }
        // Reminders and timers: the next one counts down; up to three are listed.
        const rem = (shell.system || {}).reminders || []
        if (rem.length) {
            const r = rem[0], now = Date.now() / 1000, span = Math.max(1, r.due - r.created)
            return { title: (r.kind === "timer" ? "Timer · " : "Reminder · ") + r.text + " · " + Qt.formatTime(new Date(r.due * 1000), "HH:mm"),
                     pct: Math.max(0, Math.min(100, 100 * (now - r.created) / span)), page: "",
                     steps: rem.slice(1, 4).map(x => [x.text + "  ·  " + Qt.formatTime(new Date(x.due * 1000), "HH:mm"), false]) }
        }
        return null
    }
    badge: task ? String(Math.max(1, waiting.length)) : ""
    live: task !== null
    tint: task && (task.alert || (waiting.length && !task.title.startsWith("Running"))) ? Theme.attention : Theme.accent
    onOpened: go(task ? task.page : "missions")

    Text {
        width: parent.width; elide: Text.ElideRight
        text: card.task ? card.task.title : "All quiet"
        color: Theme.text; font.pixelSize: 15
    }
    // Progress: a real percentage, or a moving light when the length is unknown.
    Item {
        visible: !!card.task && card.task.pct !== -2
        width: parent.width; height: 20
        Rectangle {
            id: track
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - (pctText.visible ? 54 : 0); height: 6; radius: 3; color: Theme.sheen(0.07)
            Rectangle {
                visible: !!card.task && card.task.pct >= 0
                height: parent.height; radius: 3
                width: parent.width * Math.max(0, Math.min(1, (card.task ? card.task.pct : 0) / 100))
                color: card.tint
                Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
            }
            Rectangle {
                visible: !!card.task && card.task.pct < 0
                height: parent.height; radius: 3; width: parent.width * 0.28; color: card.tint
                SequentialAnimation on x {
                    running: card.visible && !!card.task && card.task.pct < 0; loops: Animation.Infinite
                    NumberAnimation { from: 0; to: track.width * 0.72; duration: 1100; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 0; duration: 1100; easing.type: Easing.InOutSine }
                }
            }
        }
        Text { id: pctText; visible: !!card.task && card.task.pct >= 0; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
               text: (card.task ? Math.round(card.task.pct) : 0) + "%"; color: Theme.text; font.pixelSize: 14 }
    }
    Repeater {
        model: card.task ? card.task.steps : []
        delegate: Row {
            required property var modelData
            required property int index
            readonly property bool done: modelData[1]
            readonly property bool current: !done && (index === 0 || card.task.steps[index - 1][1])
            spacing: 12
            Item {
                width: 18; height: 18; anchors.verticalCenter: parent.verticalCenter
                Glyph { visible: parent.parent.done; anchors.fill: parent; kind: "check"; stroke: Theme.accent }
                Rectangle { visible: !parent.parent.done; anchors.centerIn: parent; width: 15; height: 15; radius: 7.5; color: "transparent"
                            border.width: 1.5; border.color: parent.parent.current ? Theme.accent : Theme.muted
                            SequentialAnimation on opacity { running: !!parent.parent.current && card.visible; loops: Animation.Infinite
                                NumberAnimation { to: 0.35; duration: 700 } NumberAnimation { to: 1; duration: 700 } } }
            }
            Text { text: modelData[0]; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 13
                   color: parent.done ? Theme.muted : parent.current ? Theme.text : Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, 0.55) }
        }
    }
    HudButton {
        visible: !!card.task && !!card.task.alert && !!card.task.actionLabel
        width: 190; implicitHeight: 32; tone: "warning"; caption: card.task ? card.task.actionLabel || "" : ""
        onClicked: card.go(card.task.page)
    }
    Text {
        visible: !card.task
        width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 12
        text: "Nothing is running. Missions, downloads and updates show their progress here."
    }
}
