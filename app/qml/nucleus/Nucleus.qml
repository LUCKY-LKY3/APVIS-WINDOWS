import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "../theme"
import "../home"

// The APVIS Nucleus: engineered frame + particle sphere, driven only by typed
// state from the shell bridge. Chooses the GPU tier or the CPU (Safe Graphics)
// tier, eases between states, and morphs sphere / aperture / globe.
Item {
    id: root
    // --- inputs from the shell bridge -----------------------------------
    property string renderer: "sphere3d"          // "sphere3d" | "canvas"
    property int particles: 8000
    property string canvasPoints: "[]"             // JSON floats, 10 per particle
    property var motion: ({})                      // MotionProfile values
    property string shape: "sphere"                // sphere | aperture | globe
    property var pin: null                         // {lat, lon, label, source}
    property bool preview: false                   // developer fixture active
    property bool reducedMotion: false
    property bool hasFocus: false
    property int approvals: 0
    property int running: 0
    property int attention: 0
    property string modeText: "IDLE"
    property color modeColor: Theme.muted
    // Live readouts on the core ring (real values; -1 = not measured).
    property real cpu: -1
    property real memory: -1
    property bool aiOnline: false
    property string aiWord: ""
    // Extra light layers (bloom, corona, rim light, orbiting lights): off on
    // the lite look (no GPU), where every layer is filled by the CPU.
    property bool rich: true
    // The owner's concept core (2026-09-26): a dark planet in green smoke.
    // false = the earlier particle sphere with HUD rings.
    property bool orbStyle: true
    // With a GPU the orb advances with the display's own refresh (vsync), not the
    // 30/20 Hz event-loop clock the CPU renderer needs.
    property bool vsync: false
    property real expanded: 0                      // 0..1 while Home grows the core for an answer
    property real orbScale: 1                      // the orb's size within this item (Home grows it while answering)
    property real answerScale: 1                   // the orb's size once an answer is showing (the text sits inside it)
    property string orbMode: "idle"
    property string orbWord: "READY"
    property color orbWordColour: Theme.accent
    // Ask: the aperture's reading plane shows the real question and answer.
    property var answer: ({ state: "closed" })     // {state, question, answer, meta, error}
    readonly property bool answering: (answer.state || "closed") !== "closed"
    signal closeAnswer()
    signal approveMission(string missionId, string token)
    signal cancelMission(string missionId)
    readonly property var mission: answer.mission || null
    readonly property bool missionMode: answer.state === "mission" && mission !== null
    signal acceptMemory(string proposalId)
    signal rejectMemory(string proposalId)
    readonly property var proposal: answer.proposal || null
    readonly property bool memoryMode: answer.state === "memory" && proposal !== null
    function missionLabel(status) {
        return status === "approval_required" ? Theme.label("NEEDS YOUR APPROVAL") :
               status === "completed" ? "DONE" + (mission && mission.verified ? "  ·  CHECKED" : "") :
               status === "failed" ? "DID NOT COMPLETE" :
               status === "cancelled" ? "CANCELLED  ·  NOTHING WAS CHANGED" :
               status === "running" ? "RUNNING…" : status.toUpperCase()
    }

    // --- animated state ---------------------------------------------------
    property real time: 0
    property real yaw: 0
    property real pitch: 0
    readonly property bool animating: visible && !reducedMotion
        && Window.window !== null && Window.window.visibility !== Window.Minimized
        && Window.window.visibility !== Window.Hidden
    property bool threeDFailed: false
    readonly property string activeRenderer: threeDFailed ? "canvas" : renderer

    property real energy: 0.55 + 0.6 * (motion.core_intensity || 0.44)
    property real turbulence: motion.turbulence || 0.1
    property real orbit: motion.orbit_speed || 0.16
    property real spin: motion.rotation_speed || 0.12
    property real breathing: motion.breathing || 0.45
    property real expansion: motion.expansion || 0
    Behavior on energy { NumberAnimation { duration: 700; easing.type: Easing.InOutQuad } }
    Behavior on turbulence { NumberAnimation { duration: 700; easing.type: Easing.InOutQuad } }
    Behavior on orbit { NumberAnimation { duration: 900; easing.type: Easing.InOutQuad } }
    Behavior on spin { NumberAnimation { duration: 900; easing.type: Easing.InOutQuad } }
    Behavior on breathing { NumberAnimation { duration: 900 } }
    Behavior on expansion { NumberAnimation { duration: 700 } }
    readonly property real breath: breathing * 0.035 * Math.sin(time * 0.9) + expansion * 0.1

    property real globe: shape === "globe" ? 1 : 0
    property real aperture: shape === "aperture" ? 1 : 0
    Behavior on globe { NumberAnimation { duration: 900; easing.type: Easing.InOutCubic } }
    Behavior on aperture { NumberAnimation { duration: 750; easing.type: Easing.InOutCubic } }

    readonly property bool pinned: shape === "globe" && pin !== null
    readonly property real targetYaw: pinned ? -pin.lon * Math.PI / 180 : 0
    readonly property real targetPitch: pinned ? pin.lat * Math.PI / 180 : 0

    function wrapAngle(a) {
        while (a > Math.PI) a -= 2 * Math.PI
        while (a < -Math.PI) a += 2 * Math.PI
        return a
    }

    function advance(dt) {
        dt = Math.min(dt, 0.1)
        root.time += dt
        hud.step(dt)
        if (root.pinned) {
            const k = 1 - Math.exp(-3 * dt)
            root.yaw += root.wrapAngle(root.targetYaw - root.yaw) * k
            root.pitch += (root.targetPitch - root.pitch) * k
        } else {
            root.yaw = root.wrapAngle(root.yaw + dt * (0.03 + root.spin * 0.22))
            root.pitch += (0 - root.pitch) * (1 - Math.exp(-2 * dt))
        }
    }

    // Frame pacing (V4, measured: an idle Home redrew 100+ times a second and kept a CPU core ~70% busy).
    // The display's full rate only while APVIS works (thinking, writing an answer) or the core is growing or
    // morphing; at rest a calm clock (idlePace, lowered by Home when nobody is using it); nothing at all while
    // paused (another app has focus). One clock drives the whole core, so frames never double up.
    property int idlePace: 24
    property bool paused: false
    property bool smooth: false                     // APVIS for Windows: the GPU draws the core, so run it at the display rate
    readonly property bool fullRate: smooth || orbMode === "thinking" || answer.state === "streaming" || answer.state === "thinking"
        || (expanded > 0.01 && expanded < 0.99) || (globe > 0.01 && globe < 0.99) || (aperture > 0.01 && aperture < 0.99)
    readonly property bool gpuClock: root.activeRenderer === "sphere3d" || (root.orbStyle && root.vsync)
    // GPU tier, working: advance with the render loop (vsync-paced).
    FrameAnimation {
        running: root.animating && !root.paused && root.gpuClock && root.fullRate
        onTriggered: root.advance(frameTime)
    }
    // GPU tier, at rest: a paced clock.
    Timer {
        interval: Math.round(1000 / Math.max(1, root.idlePace))
        repeat: true
        running: root.animating && !root.paused && root.gpuClock && !root.fullRate && root.idlePace > 0
        property real last: 0
        onRunningChanged: last = 0
        onTriggered: {
            const now = Date.now()
            root.advance(last > 0 ? (now - last) / 1000 : interval / 1000)
            last = now
        }
    }
    // CPU tier: the software scene graph does not drive a continuous render
    // loop (QML timers stall with it), so the shell supplies an event-loop
    // clock at ~30 fps and the Nucleus advances from it.
    property real clock: 0
    property real lastClock: 0
    onClockChanged: {
        if (root.animating && !root.paused && root.activeRenderer === "canvas" && !(root.orbStyle && root.vsync) && lastClock > 0)
            root.advance(clock - lastClock)
        lastClock = clock
    }

    HudCore {
        id: hud
        anchors.fill: parent
        visible: root.orbStyle && Theme.coreStyle === "hud" && opacity > 0.01
        time: root.time
        still: root.reducedMotion
        rich: root.rich
        mode: root.orbMode
        word: root.orbWord
        wordColour: root.orbWordColour
        opacity: 1 - root.globe
        scale: root.orbScale
        centreOpacity: 1 - root.aperture
        expanded: root.expanded
    }
    // APVIS 7's Neural Fabric (the "neural" look): a particle field; V7 advanced its phase ~22/s at rest.
    property bool gaming: false
    FabricCore {
        anchors.fill: parent
        visible: root.orbStyle && Theme.coreStyle === "fabric" && opacity > 0.01
        opacity: 1 - root.globe
        scale: root.orbScale
        reducedMotion: root.reducedMotion
        phase: root.time * (root.orbMode === "thinking" ? 56 : 22)
        mode: root.orbMode === "thinking" || root.orbMode === "answering" ? "answer"
            : root.orbMode === "attention" ? "mission" : root.gaming ? "gaming" : "standby"
    }
    JarvisCore {
        anchors.fill: parent
        visible: root.orbStyle && Theme.coreStyle === "jarvis" && opacity > 0.01
        time: root.time
        still: root.reducedMotion
        mode: root.orbMode
        opacity: 1 - root.globe
        scale: root.orbScale
        centreOpacity: 1 - root.aperture
    }
    InstrumentCore {
        anchors.fill: parent
        visible: root.orbStyle && Theme.coreStyle === "instrument" && opacity > 0.01
        time: root.time
        still: root.reducedMotion
        rich: root.rich
        mode: root.orbMode
        word: root.orbWord
        wordColour: root.orbWordColour
        opacity: 1 - root.globe
        scale: root.orbScale
        centreOpacity: 1 - root.aperture
        expanded: root.expanded
    }
    CoreOrb {
        anchors.fill: parent
        visible: root.orbStyle && Theme.coreStyle === "smoke" && opacity > 0.01
        time: root.time
        still: root.reducedMotion
        rich: root.rich
        mode: root.orbMode
        word: root.orbWord
        wordColour: root.orbWordColour
        opacity: 1 - root.globe
        scale: root.orbScale
        centreOpacity: 1 - root.aperture
        expanded: root.expanded
    }

    NucleusGlow {
        anchors.fill: parent
        visible: root.rich && !root.orbStyle
        time: root.time
        energy: root.energy
        reducedMotion: root.reducedMotion
        opacity: 1 - 0.55 * Math.max(root.globe, root.aperture)
    }

    NucleusFrame {
        anchors.fill: parent
        visible: !root.orbStyle
        hasFocus: root.hasFocus
        approvals: root.approvals
        running: root.running
        attention: root.attention
    }

    NucleusFabric {
        anchors.fill: parent
        time: root.time
        reducedMotion: root.reducedMotion
        opacity: 1 - Math.max(root.globe, root.aperture)
        visible: !root.orbStyle && opacity > 0.01
    }

    NucleusRings {
        anchors.fill: parent
        visible: !root.orbStyle
        time: root.time
        reducedMotion: root.reducedMotion
        opacity: 1 - 0.7 * Math.max(root.globe, root.aperture)
    }

    NucleusGauges {
        anchors.fill: parent
        cpu: root.cpu
        memory: root.memory
        aiOnline: root.aiOnline
        aiWord: root.aiWord
        opacity: 1 - Math.max(root.globe, root.aperture)
        visible: !root.orbStyle && opacity > 0.01
    }

    Loader {
        id: loader
        anchors.fill: parent
        // The particle sphere: the classic core, or the globe preview (pins).
        active: !root.orbStyle || root.globe > 0.001 || root.shape === "globe"
        source: root.activeRenderer === "sphere3d" ? "NucleusSphere3D.qml" : "NucleusCanvas.qml"
        onStatusChanged: if (status === Loader.Error && root.activeRenderer === "sphere3d") root.threeDFailed = true
        onLoaded: {
            const names = ["time", "yaw", "pitch", "breath", "turbulence", "orbit", "energy", "globe", "aperture"]
            for (const n of names)
                item[n] = Qt.binding((function (name) { return function () { return root[name] } })(n))
            item.tint = Qt.binding(function () { return Theme.accent })
            item.warm = Qt.binding(function () { return Theme.warm })
            if ("particles" in item) item.particles = Qt.binding(function () { return root.particles })
            if ("points" in item) item.points = Qt.binding(function () { return root.canvasPoints })
        }
    }

    NucleusOrbits {
        anchors.fill: parent
        time: root.time
        visible: root.rich && !root.orbStyle && !root.reducedMotion && opacity > 0.01
        opacity: 1 - Math.max(root.globe, root.aperture)
    }

    // Wordmark and state text sit in the clear centre (hidden while morphed).
    Column {
        anchors.centerIn: parent
        spacing: 4
        opacity: 1 - Math.max(root.globe, root.aperture)
        visible: !root.orbStyle && opacity > 0.01
        // The APVIS emblem, softly glowing, above the wordmark (owner concept 364fcddd).
        Item {
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.max(36, root.width * 0.085); height: width
            Glyph { anchors.centerIn: parent; width: parent.width * 1.5; height: width; kind: "apvis"; stroke: Theme.accent; accent: Theme.accent; opacity: .16 }
            Glyph { anchors.centerIn: parent; width: parent.width * 1.2; height: width; kind: "apvis"; stroke: Theme.accent; accent: Theme.accent; opacity: .22 }
            Glyph { anchors.fill: parent; kind: "apvis"; stroke: Theme.accent; accent: Theme.text }
        }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: Theme.label("APVIS"); color: Theme.text; font.pixelSize: Math.max(18, root.width * 0.036); font.letterSpacing: 8 }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter; spacing: 7
            Rectangle { width: 5; height: 5; radius: 2.5; anchors.verticalCenter: parent.verticalCenter
                        color: root.modeText === "IDLE" ? Theme.accent : root.modeColor
                        // Only while this (pre-V3) wordmark shows: a hidden endless animation kept Home redrawing
                        // at the display's full rate even when nothing on screen moved (V4).
                        SequentialAnimation on opacity { running: root.animating && !root.orbStyle && !root.paused; loops: Animation.Infinite
                            NumberAnimation { to: 0.25; duration: 1100; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1; duration: 1100; easing.type: Easing.InOutSine } } }
            Text { text: root.modeText; color: root.modeColor; font.pixelSize: 10; font.letterSpacing: 2 }
        }
    }

    // Answer Focus reading plane: stable, clear, never over moving particles.
    Item {
        id: plane
        anchors.centerIn: parent
        // Orb style: the answer sits inside the dark sphere, no box around it.
        width: root.orbStyle ? Math.min(parent.width, parent.height) * 0.5 * root.answerScale * 0.7
                             : Math.min(parent.width, parent.height) * (root.answering ? 0.7 : 0.62)
        height: root.orbStyle ? width * 0.86 : width * (root.answering ? 0.72 : 0.62)
        opacity: root.aperture
        visible: opacity > 0.01
        Chamfer {
            visible: !root.orbStyle
            anchors.fill: parent; cut: 18
            fill: Theme.raised; fillOpacity: root.answering ? 0.9 : 0.55
            fill2: Theme.bgBottom; fill2Opacity: root.answering ? 0.94 : 0.55
            stroke: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.45)
            brackets: true; edgeGlow: true
        }
        // Scanning light along the top while the model is thinking.
        Rectangle {
            visible: root.answer.state === "thinking" || root.answer.state === "streaming"
            y: 0; height: 2; width: parent.width * 0.25; radius: 1
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 0.5; color: Theme.accent }
                GradientStop { position: 1; color: "transparent" } }
            SequentialAnimation on x {
                running: parent.visible && root.animating; loops: Animation.Infinite
                NumberAnimation { from: 18; to: plane.width - plane.width * 0.25 - 18; duration: 1400; easing.type: Easing.InOutSine }
                NumberAnimation { to: 18; duration: 1400; easing.type: Easing.InOutSine }
            }
        }
        Column {
            visible: !root.answering
            anchors.centerIn: parent
            width: parent.width - 40
            spacing: 8
            Text { width: parent.width; text: root.preview ? Theme.label("DEVELOPER PREVIEW") : ""; color: Theme.attention; font.pixelSize: 10; font.letterSpacing: 2; horizontalAlignment: Text.AlignHCenter }
            Text { width: parent.width; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; color: Theme.text; font.pixelSize: 14
                   text: "Answer Focus reading plane. Answers and pictures appear here with their sources once Ask is connected." }
        }
        Item {
            visible: root.answering
            anchors.fill: parent
            anchors.margins: 20
            Text {
                id: askedLabel
                width: parent.width - 36
                text: root.answer.question || ""
                color: Theme.muted; font.pixelSize: 12
                elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.WordWrap
            }
            Button {
                id: closeButton
                anchors.right: parent.right; y: -6
                width: 30; height: 30
                Accessible.name: "Close answer"
                contentItem: Text { text: "×"; color: Theme.text; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 15; color: closeButton.hovered || closeButton.activeFocus ? Theme.hover : "transparent" }
                onClicked: root.closeAnswer()
            }
            Rectangle { id: rule; y: askedLabel.height + 10; width: parent.width; height: 1; color: Theme.line }
            Column {
                id: memoryCard
                visible: root.memoryMode
                y: rule.y + 14
                width: parent.width
                spacing: 10
                Text {
                    text: !root.proposal ? "" : root.proposal.status === "accepted" ? Theme.label("SAVED TO YOUR VAULT") :
                          root.proposal.status === "rejected" ? "NOT SAVED" :
                          root.proposal.kind === "decision" ? "SAVE THIS DECISION?" : "REMEMBER THIS?"
                    color: root.proposal && root.proposal.status === "pending" ? Theme.attention : Theme.accent
                    font.pixelSize: 11; font.letterSpacing: 2
                }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap
                    text: root.proposal ? root.proposal.text : ""
                    color: Theme.text; font.pixelSize: 17
                }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap
                    visible: text.length > 0
                    color: Theme.muted; font.pixelSize: 12
                    text: !root.proposal ? "" : root.proposal.status !== "pending" ? (root.answer.answer || "") :
                          (root.proposal.reason ? "Why: " + root.proposal.reason + "\n" : "") +
                          (root.proposal.similar.length ? "Similar notes you already have: " + root.proposal.similar.join(", ") + "\n" : "") +
                          "Saved as a Markdown note in your vault only if you accept. Stays on this device."
                }
                Row {
                    visible: !!root.proposal && root.proposal.status === "pending"
                    spacing: 10
                    HudButton {
                        width: 120; implicitHeight: 38; caption: "Save"; glyph: "check"; tone: "primary"
                        Accessible.name: "Save to vault"
                        onClicked: root.acceptMemory(root.proposal.id)
                    }
                    HudButton {
                        width: 120; implicitHeight: 38; caption: "Don't save"
                        onClicked: root.rejectMemory(root.proposal.id)
                    }
                }
            }
            Column {
                id: missionCard
                visible: root.missionMode
                y: rule.y + 14
                width: parent.width
                spacing: 10
                Text {
                    text: root.mission ? root.missionLabel(root.mission.status) : ""
                    color: root.mission && (root.mission.status === "approval_required" || root.mission.status === "failed") ? Theme.attention : Theme.accent
                    font.pixelSize: 11; font.letterSpacing: 2
                }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap
                    text: root.mission ? root.mission.preview : ""
                    color: Theme.text; font.pixelSize: 18
                }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap
                    visible: text.length > 0
                    text: !root.mission ? "" :
                          root.mission.status === "approval_required" ?
                              (root.mission.permission === "DESTRUCTIVE" ? "This can lose unsaved work or remove a file from where it is. " : "") +
                              "Nothing happens until you approve. The request expires in 10 minutes." :
                          (root.mission.message || root.mission.error || "")
                    color: root.mission && root.mission.status === "failed" ? Theme.attention : Theme.muted
                    font.pixelSize: 13
                }
                Row {
                    visible: !!root.mission && root.mission.status === "approval_required"
                    spacing: 10
                    HudButton {
                        width: 124; implicitHeight: 38; caption: "Approve"; glyph: "check"; tone: "primary"
                        Accessible.name: "Approve: " + (root.mission ? root.mission.preview : "")
                        onClicked: root.approveMission(root.mission.id, root.mission.token)
                    }
                    HudButton {
                        width: 104; implicitHeight: 38; caption: "Cancel"
                        onClicked: root.cancelMission(root.mission.id)
                    }
                }
            }
            Flickable {
                id: answerScroll
                visible: !root.missionMode && !root.memoryMode
                y: rule.y + 12
                width: parent.width
                height: parent.height - y - metaLabel.height - 10
                clip: true
                contentHeight: answerText.height
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: HudScrollBar { policy: answerScroll.contentHeight > answerScroll.height ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded }
                Text {
                    id: answerText
                    width: answerScroll.width - 12
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                    color: root.answer.state === "error" ? Theme.attention : Theme.text
                    font.pixelSize: 15; lineHeight: 1.25
                    font.family: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family
                    text: root.answer.state === "error" ? (root.answer.error || "Ask failed") :
                          (root.answer.answer || (root.answer.state === "thinking" ? "Thinking…" : ""))
                    // Follow the stream while the model is writing.
                    onHeightChanged: if (root.answer.state === "streaming" && height > answerScroll.height)
                                         answerScroll.contentY = height - answerScroll.height
                }
            }
            Text {
                id: metaLabel
                anchors.bottom: parent.bottom
                width: parent.width
                text: root.missionMode ? Theme.label("MISSION CONTROL  ·  CHECKED AFTERWARDS  ·  LOGGED") :
                      root.memoryMode ? "MEMORY INBOX  ·  NOTHING IS SAVED WITHOUT YOU" :
                      root.answer.state === "done" ? "Answered by " + (root.answer.meta || "") :
                      root.answer.state === "error" ? "Nothing was sent outside this machine or your network." :
                      "Local model is answering…"
                color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1
                elide: Text.ElideRight
            }
        }
    }

    // Globe pin: the pinned place is rotated to face the viewer, i.e. the centre.
    Item {
        anchors.centerIn: parent
        width: 1; height: 1
        visible: root.pinned && root.globe > 0.9
        Rectangle { anchors.centerIn: parent; width: 16; height: 16; radius: 8; color: "transparent"; border.color: Theme.attention; border.width: 2 }
        Rectangle { anchors.centerIn: parent; width: 5; height: 5; radius: 2.5; color: Theme.attention }
        Column {
            x: 16; y: -8
            Text { text: root.pin ? root.pin.label : ""; color: Theme.text; font.pixelSize: 13 }
            Text { text: root.pin ? (root.preview ? "Developer preview · " : "") + root.pin.source : ""; color: Theme.muted; font.pixelSize: 10 }
        }
    }

    Accessible.role: Accessible.Graphic
    Accessible.name: "APVIS Nucleus: " + root.modeText + (root.pinned ? ", showing " + root.pin.label : "")
}
