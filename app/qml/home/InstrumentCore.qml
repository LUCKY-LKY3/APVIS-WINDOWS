import QtQuick
import "../theme"

// The V3 APVIS core (lacquer and brass): a brass instrument round a black lacquer sphere, not a flame.
// Pre-rendered layers (qml/art/instrument-*.png, scripts/generate-instrument-core.py); per frame only
// rotation and opacity change, so it stays cheap on the OptiPlex GPU and on the CPU renderer.
// Calm at rest; when APVIS works, the escapement ticks, the meridian turns and light runs round the bezel.
// The light on the brass is its own still layer, so the metal turns under it like the real thing.
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
    // The brass reaches further out than the V2 smoke did, so the whole instrument sits a little smaller.
    readonly property real box: Math.min(width, height) * 0.86
    readonly property real sphere: box * 0.5

    property real energy: mode === "thinking" ? 1.0 : mode === "answering" ? 0.7 : mode === "attention" ? 0.5 : 0.12
    Behavior on energy { NumberAnimation { duration: 1100; easing.type: Easing.InOutQuad } }
    // Integrated, so a change of pace never snaps a ring. At rest it barely moves.
    property real phase: 0
    property real lastTime: 0
    onTimeChanged: {
        const dt = Math.min(0.1, Math.max(0, time - lastTime))
        lastTime = time
        if (!still) phase += dt * (0.12 + 1.5 * energy)
    }
    readonly property real breath: still ? 0 : Math.sin(time * 0.6)
    function art(name) { return Theme.artDir ? Theme.artDir + name : "../art/" + name }

    component Layer: Image {
        anchors.centerIn: parent
        width: orb.box; height: orb.box
        sourceSize: Qt.size(1024, 1024)
        smooth: true; mipmap: true
        fillMode: Image.Stretch
    }

    Layer {                     // its shadow on the lacquer: lifts the instrument off the room
        source: orb.art("instrument-shadow.png")
        scale: 1.04
    }
    // A faint warm pool behind the instrument (light on lacquer, not glow).
    Canvas {
        id: pool
        visible: !orb.lean
        anchors.centerIn: parent
        width: orb.box * 1.25; height: width
        opacity: 0.55 + 0.45 * orb.energy + 0.05 * orb.breath
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()
        Connections { target: Theme; function onAccentNameChanged() { pool.requestPaint() } }
        onPaint: {
            const c = getContext("2d"), r = width / 2
            c.reset()
            const g = c.createRadialGradient(r, r, r * 0.35, r, r, r)
            g.addColorStop(0, Theme.css(Theme.accent, 0.10)); g.addColorStop(0.5, Theme.css(Theme.accent, 0.04))
            g.addColorStop(1, Theme.css(Theme.accent, 0))
            c.fillStyle = g; c.fillRect(0, 0, width, height)
        }
    }

    Layer {                     // hairline orbit with jewels
        visible: !orb.lean
        source: orb.art("instrument-orbit.png")
        rotation: (orb.phase * -1.1) % 360
        opacity: 0.75 + 0.25 * orb.energy
    }
    // A tilted ring precessing round the sphere: its far half passes behind, its near half in front.
    readonly property real precession: (orb.phase * 3.2 + 18) % 360
    Layer {
        visible: !orb.lean
        source: orb.art("instrument-tilt-back.png")
        rotation: orb.precession
    }
    Layer {                     // armillary meridian
        visible: !orb.lean
        source: orb.art("instrument-meridian.png")
        rotation: (30 + orb.phase * 5) % 360
    }
    Layer {                     // engraved bezel: drifts, never spins
        source: orb.art("instrument-bezel.png")
        rotation: (orb.phase * -0.6) % 360
    }
    Layer {                     // escapement: ticks in steps, like a watch
        source: orb.art("instrument-gear.png")
        rotation: orb.still ? 0 : (Math.floor(orb.phase * 10) * 1.0) % 360
    }
    Layer { source: orb.art("instrument-sphere.png") }
    Layer {                     // warm light deep in the lacquer, seen through the dial; brightens while APVIS works
        source: orb.art("instrument-inner.png")
        opacity: 0.08 + 0.75 * orb.energy + 0.04 * orb.breath
    }
    Layer {                     // the still light on the brass
        source: orb.art("instrument-light.png")
        opacity: 0.8 + 0.2 * orb.energy + 0.04 * orb.breath
    }
    Layer {
        visible: !orb.lean
        source: orb.art("instrument-tilt-front.png")
        rotation: orb.precession
    }
    Layer {                     // light running round the bezel while APVIS works
        source: orb.art("instrument-glint.png")
        visible: opacity > 0.01
        rotation: (orb.phase * 46) % 360
        opacity: orb.still ? 0 : Math.max(0, (orb.energy - 0.3) / 0.7)
    }
    // Needs you: a thin cool arc (the attention colour), never red unless critical.
    Canvas {
        id: attention
        anchors.centerIn: parent
        width: orb.box * 0.70; height: width
        visible: opacity > 0.01
        opacity: orb.mode === "attention" ? 0.85 : 0
        Behavior on opacity { NumberAnimation { duration: 600 } }
        rotation: (orb.phase * 12) % 360
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()
        onPaint: {
            const c = getContext("2d"), r = width / 2 - 3
            c.reset()
            c.lineWidth = 2; c.lineCap = "round"
            c.strokeStyle = Theme.css(Theme.attention, 0.9)
            c.beginPath(); c.arc(width / 2, height / 2, r, -0.6, 0.6); c.stroke()
            c.beginPath(); c.arc(width / 2, height / 2, r, Math.PI - 0.6, Math.PI + 0.6); c.stroke()
        }
    }

    // Centre: the mark, the name in APVIS's own voice, the state, and a quiet activity line.
    Column {
        id: centre
        anchors.centerIn: parent
        opacity: orb.centreOpacity
        visible: opacity > 0.01
        anchors.verticalCenterOffset: orb.sphere * 0.04
        spacing: orb.sphere * 0.035
        ApvisMark {
            anchors.horizontalCenter: parent.horizontalCenter
            width: orb.sphere * 0.24; height: width * 0.88
            glow: Theme.markGlow * (0.6 + 0.4 * orb.energy)
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Theme.label("APVIS"); color: Theme.text
            font.pixelSize: Math.max(18, orb.sphere * 0.10); font.weight: Font.Normal
            font.family: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family
            font.letterSpacing: Math.max(5, orb.sphere * 0.045)
            leftPadding: font.letterSpacing
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Theme.label(orb.word); color: orb.wordColour
            font.pixelSize: Math.max(10, orb.sphere * 0.036)
            font.family: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family
            font.italic: !Theme.caps; font.letterSpacing: Theme.caps ? 2.5 : 0.6
            leftPadding: font.letterSpacing
        }
        // A single engraved line that stirs while APVIS works (no bars, no noise at rest).
        Item {
            id: wave
            anchors.horizontalCenter: parent.horizontalCenter
            width: orb.sphere * 0.5; height: orb.sphere * 0.07
            Canvas {
                id: line
                anchors.fill: parent
                property real t: orb.time
                property real e: orb.energy
                // Repaint only while there is something to show moving (cheap at rest).
                onTChanged: if (!orb.still && (e > 0.2 || frame++ % 15 === 0)) requestPaint()
                property int frame: 0
                onPaint: {
                    const c = getContext("2d"), w = width, h = height
                    c.reset()
                    const grad = c.createLinearGradient(0, 0, w, 0)
                    grad.addColorStop(0, Theme.css(orb.wordColour, 0)); grad.addColorStop(0.5, Theme.css(orb.wordColour, 0.9))
                    grad.addColorStop(1, Theme.css(orb.wordColour, 0))
                    c.strokeStyle = grad; c.lineWidth = 1.2
                    c.beginPath()
                    for (let i = 0; i <= 64; i++) {
                        const f = i / 64, bell = Math.exp(-Math.pow((f - 0.5) / 0.22, 2))
                        const y = h / 2 + Math.sin(f * 22 + t * 3.2) * Math.sin(f * 7 - t * 1.3) * bell * h * 0.42 * (0.08 + 0.92 * e)
                        if (i === 0) c.moveTo(0, y); else c.lineTo(f * w, y)
                    }
                    c.stroke()
                }
            }
        }
    }
    Accessible.role: Accessible.Graphic
    Accessible.name: "APVIS core: " + word
}
