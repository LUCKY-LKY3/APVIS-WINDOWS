import QtQuick
import "../theme"

// The V3 APVIS core, JARVIS style (owner, 2026-10-06): rings of glowing gold light round a dark plate,
// an arc-reactor ring, a tick scale, data segments and a sweep. Pre-rendered layers
// (qml/art/hud-*.png, scripts/generate-hud-core.py); per frame only rotation and opacity change, so it
// stays cheap on the OptiPlex GPU and on the CPU renderer. Always gently turning; when APVIS works the
// rings speed up, the reactor brightens and the sweep runs.
Item {
    id: orb
    property real time: 0
    property bool still: false
    property bool rich: true
    property string mode: "idle"                 // idle | thinking | answering | attention
    property string word: "READY"
    property color wordColour: Theme.accent
    property real expanded: 0
    readonly property bool lean: expanded > 0.01 || !rich
    property real centreOpacity: 1
    readonly property real box: Math.min(width, height) * 0.86
    readonly property real sphere: box * 0.5

    property real energy: mode === "thinking" ? 1.0 : mode === "answering" ? 0.75 : mode === "attention" ? 0.55 : 0.18
    Behavior on energy { NumberAnimation { duration: 900; easing.type: Easing.InOutQuad } }
    property real phase: 0
    property real lastTime: 0
    // Turned by the Nucleus clock (full rate while APVIS works, paced at rest; V4).
    function step(dt) {
        if (!orb.still && orb.visible)
            orb.phase += Math.min(0.1, dt) * (0.35 + 1.5 * orb.energy)
    }
    readonly property real breath: still ? 0 : Math.sin(time * 1.1)
    function art(name) { return Theme.artDir ? Theme.artDir + name : "../art/" + name }

    component Layer: Image {
        anchors.centerIn: parent
        width: orb.box; height: orb.box
        sourceSize: Qt.size(1024, 1024)
        smooth: true; mipmap: true
        fillMode: Image.Stretch
    }

    Layer { source: orb.art("hud-haze.png"); opacity: 0.6 + 0.4 * orb.energy }
    Layer { source: orb.art("hud-outer.png"); rotation: (orb.phase * 2.0) % 360 }
    Layer { source: orb.art("hud-ticks.png"); rotation: (orb.phase * -0.6) % 360; opacity: 0.85 }
    Layer { visible: !orb.lean; source: orb.art("hud-segments.png"); rotation: (40 - orb.phase * 4.0) % 360 }
    Layer { visible: !orb.lean; source: orb.art("hud-bands.png"); rotation: (70 + orb.phase * 7.5) % 360
            opacity: (0.7 + 0.3 * orb.energy) * (1 - 0.6 * orb.reading) }
    Layer { visible: !orb.lean; source: orb.art("hud-dots.png"); rotation: (orb.phase * 1.2) % 360 }
    // While an answer shows, the dark plate grows under the text and the inner rings dim, so it reads clearly.
    readonly property real reading: 1 - orb.centreOpacity
    Layer { source: orb.art("hud-centre.png"); scale: 1 + 0.95 * orb.reading; opacity: 1 }
    Layer {                                       // the arc reactor: breathes, brightens while APVIS works
        source: orb.art("hud-reactor.png")
        opacity: (0.6 + 0.35 * orb.energy + 0.05 * orb.breath) * (1 - 0.8 * orb.reading)
        scale: 1 + 0.006 * orb.breath
    }
    Layer { source: orb.art("hud-inner.png"); rotation: (15 - orb.phase * 5.5) % 360; opacity: 1 - 0.8 * orb.reading }
    Layer {                                       // the sweep, while APVIS thinks or answers
        source: orb.art("hud-sweep.png")
        visible: opacity > 0.01 && !orb.lean
        rotation: (orb.phase * 70) % 360
        opacity: orb.still ? 0 : Math.max(0, (orb.energy - 0.3) / 0.7)
    }
    // Needs you: two cool arcs (the attention colour), never red unless critical.
    Canvas {
        anchors.centerIn: parent
        width: orb.box * 0.98; height: width
        visible: opacity > 0.01
        opacity: orb.mode === "attention" ? 0.9 : 0
        Behavior on opacity { NumberAnimation { duration: 600 } }
        rotation: (orb.phase * 10) % 360
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()
        onPaint: {
            const c = getContext("2d"), r = width / 2 - 3
            c.reset(); c.lineWidth = 2; c.lineCap = "round"
            c.strokeStyle = Theme.css(Theme.attention, 0.9)
            c.beginPath(); c.arc(width / 2, height / 2, r, -0.5, 0.5); c.stroke()
            c.beginPath(); c.arc(width / 2, height / 2, r, Math.PI - 0.5, Math.PI + 0.5); c.stroke()
        }
    }

    // Centre: the mark, the name in APVIS's own voice, the state, and a line that stirs while it works.
    Column {
        anchors.centerIn: parent
        opacity: orb.centreOpacity
        visible: opacity > 0.01
        anchors.verticalCenterOffset: orb.sphere * 0.03
        spacing: orb.sphere * 0.03
        ApvisMark {
            visible: false                       // the mark is a miniature of this core; inside it, the name is enough
            anchors.horizontalCenter: parent.horizontalCenter
            width: orb.sphere * 0.2; height: width * 0.88
            glow: Theme.markGlow * (0.8 + 0.6 * orb.energy)
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Theme.label("APVIS"); color: Theme.text
            font.pixelSize: Math.max(16, orb.sphere * 0.085); font.weight: Font.Normal
            font.family: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family
            font.letterSpacing: Math.max(5, orb.sphere * 0.04)
            leftPadding: font.letterSpacing
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Theme.label(orb.word); color: orb.wordColour
            font.pixelSize: Math.max(10, orb.sphere * 0.032)
            font.family: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family
            font.italic: !Theme.caps; font.letterSpacing: Theme.caps ? 2.5 : 0.6
            leftPadding: font.letterSpacing
        }
    }
    Accessible.role: Accessible.Graphic
    Accessible.name: "APVIS core: " + word
}
