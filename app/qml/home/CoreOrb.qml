import QtQuick
import "../theme"

// The APVIS core (owner concept, 2026-09-26): a dark planet wrapped in green
// energy smoke, the APVIS mark and wordmark inside, and a waveform that shows
// what APVIS is doing. The smoke and sphere are pre-rendered textures
// (qml/art, scripts/generate-core-art.py); per frame only rotation, scale and
// opacity change, so it is cheap on the OptiPlex GPU and on the CPU renderer.
Item {
    id: orb
    property real time: 0
    property bool still: false
    property bool rich: true                     // extra layers (off on the lite look)
    property string mode: "idle"                 // idle | thinking | answering | attention
    property string word: "READY"
    property color wordColour: Theme.accent
    // While grown for an answer the orb covers far more pixels; the extra glow
    // layers step aside so the OptiPlex GPU keeps its frame rate.
    property real expanded: 0
    readonly property bool lean: expanded > 0.01 || !rich
    property real centreOpacity: 1               // the mark and words fade while an answer sits on top
    readonly property real box: Math.min(width, height)          // texture box; the sphere is half of it
    readonly property real sphere: box * 0.5

    // Energy follows what APVIS is doing (eased, never jumps).
    property real energy: mode === "thinking" ? 1.0 : mode === "answering" ? 0.8 : mode === "attention" ? 0.6 : 0.25
    Behavior on energy { NumberAnimation { duration: 900; easing.type: Easing.InOutQuad } }
    // Swirl phase: integrated, so a speed change never snaps the layers.
    property real phase: 0
    property real lastTime: 0
    onTimeChanged: {
        const dt = Math.min(0.1, Math.max(0, time - lastTime))
        lastTime = time
        if (!still) phase += dt * (0.6 + 1.6 * energy)
    }
    readonly property real breath: still ? 0 : Math.sin(time * 0.8)

    component Layer: Image {
        anchors.centerIn: parent
        width: orb.box; height: orb.box
        sourceSize: Qt.size(1024, 1024)
        smooth: true; mipmap: true
        fillMode: Image.Stretch
    }

    // Soft light pooled behind the planet.
    Canvas {
        id: pool
        visible: !orb.lean
        anchors.centerIn: parent
        width: orb.box * 1.3; height: width
        opacity: 0.75 + 0.25 * orb.energy + 0.08 * orb.breath
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()
        Connections { target: Theme; function onAccentNameChanged() { pool.requestPaint() } }
        onPaint: {
            const c = getContext("2d"), r = width / 2, a = Theme.accent
            const rgb = Math.round(a.r * 255) + "," + Math.round(a.g * 255) + "," + Math.round(a.b * 255)
            c.reset()
            const g = c.createRadialGradient(r, r, r * 0.25, r, r, r)
            g.addColorStop(0, "rgba(" + rgb + ",0.26)"); g.addColorStop(0.35, "rgba(" + rgb + ",0.14)")
            g.addColorStop(0.6, "rgba(" + rgb + ",0.05)"); g.addColorStop(1, "rgba(" + rgb + ",0)")
            c.fillStyle = g; c.fillRect(0, 0, width, height)
        }
    }

    // Outer smoke (behind the planet): two copies, mirrored, turning apart.
    Layer {
        source: Theme.artDir ? Theme.artDir + "core-smoke-back.png" : "../art/core-smoke-back.png"
        rotation: (orb.phase * 5) % 360
        scale: 1.02 + 0.015 * orb.breath + 0.03 * orb.energy
        opacity: 0.8 + 0.2 * orb.energy
    }
    Layer {
        visible: orb.rich && !orb.lean
        source: Theme.artDir ? Theme.artDir + "core-smoke-back.png" : "../art/core-smoke-back.png"
        rotation: (200 - orb.phase * 3.4) % 360
        transform: Scale { origin.x: orb.box / 2; xScale: -1 }
        scale: 0.96 - 0.01 * orb.breath
        opacity: 0.45 + 0.25 * orb.energy
    }
    Layer { source: Theme.artDir ? Theme.artDir + "core-sphere.png" : "../art/core-sphere.png" }
    // Inner light: the planet's rim warms up while APVIS works.
    Canvas {
        id: innerLight
        visible: !orb.lean
        anchors.centerIn: parent
        width: orb.sphere; height: width
        opacity: 0.35 + 0.65 * orb.energy
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()
        Connections { target: Theme; function onAccentNameChanged() { innerLight.requestPaint() } }
        onPaint: {
            const c = getContext("2d"), r = width / 2, a = Theme.accent
            const rgb = Math.round(a.r * 255) + "," + Math.round(a.g * 255) + "," + Math.round(a.b * 255)
            c.reset()
            const g = c.createRadialGradient(r, r, r * 0.55, r, r, r)
            g.addColorStop(0, "rgba(" + rgb + ",0)"); g.addColorStop(0.8, "rgba(" + rgb + ",0.10)"); g.addColorStop(1, "rgba(" + rgb + ",0.28)")
            c.beginPath(); c.arc(r, r, r, 0, Math.PI * 2); c.fillStyle = g; c.fill()
            // A faint centre light behind the mark.
            const m = c.createRadialGradient(r, r * 0.95, 0, r, r * 0.95, r * 0.55)
            m.addColorStop(0, "rgba(" + rgb + ",0.12)"); m.addColorStop(1, "rgba(" + rgb + ",0)")
            c.fillStyle = m; c.fillRect(0, 0, width, height)
        }
    }
    Layer {
        source: Theme.artDir ? Theme.artDir + "core-smoke-mid.png" : "../art/core-smoke-mid.png"
        rotation: (40 - orb.phase * 7) % 360
        scale: 1.0 + 0.012 * orb.breath
        opacity: 0.85 + 0.15 * orb.energy
    }
    Layer {
        source: Theme.artDir ? Theme.artDir + "core-smoke-front.png" : "../art/core-smoke-front.png"
        rotation: (orb.phase * 9) % 360
        opacity: 0.9
    }

    // HUD instrument rings and orbiting points (owner, 2026-09-27). Each ring is painted once
    // and only rotated per frame; all of it steps aside while grown for an answer or on the lite look.
    component Ring: Canvas {
        id: ring
        property real radiusFrac: 0.48         // of the texture box
        property int ticks: 0
        property var arcs: []                  // [[from, to], ...] as fractions of a turn
        property real dash: 0                  // > 0: dashed circle, dash length in degrees
        property real baseAlpha: 0.35
        visible: !orb.lean
        anchors.centerIn: parent
        width: orb.box * radiusFrac * 2 + 16; height: width
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()
        Connections { target: Theme; function onAccentNameChanged() { ring.requestPaint() } }
        onPaint: {
            const c = getContext("2d"), r = width / 2 - 8, a = Theme.accent
            const col = al => "rgba(" + Math.round(a.r * 255) + "," + Math.round(a.g * 255) + "," + Math.round(a.b * 255) + "," + al + ")"
            c.reset()
            c.translate(width / 2, height / 2)
            c.lineWidth = 1
            if (dash > 0) {
                const step = dash * Math.PI / 180
                c.strokeStyle = col(baseAlpha)
                for (let t = 0; t < Math.PI * 2; t += step * 2) { c.beginPath(); c.arc(0, 0, r, t, t + step); c.stroke() }
            } else {
                c.strokeStyle = col(baseAlpha); c.beginPath(); c.arc(0, 0, r, 0, Math.PI * 2); c.stroke()
            }
            for (let i = 0; i < ticks; i++) {
                const t = i / ticks * Math.PI * 2, major = i % 10 === 0, len = major ? 9 : 4
                c.strokeStyle = col(major ? baseAlpha + 0.35 : baseAlpha)
                c.beginPath(); c.moveTo(Math.cos(t) * r, Math.sin(t) * r); c.lineTo(Math.cos(t) * (r - len), Math.sin(t) * (r - len)); c.stroke()
            }
            c.lineWidth = 2.5
            for (const seg of arcs) {
                c.strokeStyle = col(0.9)
                c.beginPath(); c.arc(0, 0, r + 4, seg[0] * Math.PI * 2, seg[1] * Math.PI * 2); c.stroke()
            }
        }
    }
    Ring {
        radiusFrac: 0.47; ticks: 120; arcs: [[0.03, 0.17], [0.47, 0.55], [0.78, 0.83]]; baseAlpha: 0.3
        rotation: (orb.phase * -2.4) % 360
        opacity: 0.55 + 0.35 * orb.energy
    }
    Ring {
        radiusFrac: 0.262; dash: 2; baseAlpha: 0.85
        rotation: (orb.phase * 4.2) % 360
        opacity: 0.35 + 0.5 * orb.energy
    }
    // Points on orbit: [radius fraction, speed, start angle, size].
    Repeater {
        model: [[0.47, 1.0, 20, 7], [0.36, -1.7, 150, 5], [0.42, 0.6, 260, 6]]
        delegate: Item {
            required property var modelData
            visible: !orb.lean
            anchors.centerIn: parent
            width: orb.box * modelData[0] * 2; height: width
            rotation: (modelData[2] + orb.phase * 14 * modelData[1]) % 360
            Rectangle {          // soft halo
                x: parent.width / 2 - width / 2; y: -width / 2
                width: parent.modelData[3] * 4; height: width; radius: width / 2
                color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.18)
            }
            Rectangle {
                x: parent.width / 2 - width / 2; y: -width / 2
                width: parent.modelData[3]; height: width; radius: width / 2
                color: Qt.lighter(Theme.accent, 1.35)
                opacity: 0.7 + 0.3 * orb.energy
            }
        }
    }

    // Centre: mark, wordmark, state and waveform.
    Column {
        id: centre
        anchors.centerIn: parent
        opacity: orb.centreOpacity
        visible: opacity > 0.01
        anchors.verticalCenterOffset: orb.sphere * 0.06
        spacing: orb.sphere * 0.03
        ApvisMark {
            anchors.horizontalCenter: parent.horizontalCenter
            width: orb.sphere * 0.27; height: width * 0.88
            glow: 0.8 + 0.4 * orb.energy
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Theme.label("APVIS"); color: Theme.text
            font.pixelSize: Math.max(18, orb.sphere * 0.105); font.weight: Font.Normal
            font.family: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family
            font.letterSpacing: Math.max(6, orb.sphere * 0.05)
            leftPadding: font.letterSpacing          // keeps the spaced word optically centred
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: orb.word; color: orb.wordColour
            font.pixelSize: Math.max(9, orb.sphere * 0.034); font.letterSpacing: 2.5
            leftPadding: 2.5
        }
        // Waveform: bell-shaped bars whose motion follows APVIS's state.
        Item {
            id: wave
            anchors.horizontalCenter: parent.horizontalCenter
            width: orb.sphere * 0.62; height: orb.sphere * 0.12
            readonly property int bars: 41
            Rectangle {       // baseline
                anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 1
                gradient: Gradient { orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 0.5; color: Qt.rgba(orb.wordColour.r, orb.wordColour.g, orb.wordColour.b, 0.8) }
                    GradientStop { position: 1; color: "transparent" } }
            }
            Repeater {
                model: wave.bars
                delegate: Rectangle {
                    required property int index
                    readonly property real f: index / (wave.bars - 1)
                    readonly property real bell: Math.exp(-Math.pow((f - 0.5) / 0.2, 2))
                    readonly property real jitter: 0.5 + 0.5 * Math.sin(orb.time * (3.1 + (index * 7 % 5)) + index * 1.7)
                                                   * Math.sin(orb.time * (1.3 + (index * 3 % 4) * 0.4) + index)
                    readonly property real amp: orb.still ? 0.18 * bell : bell * (0.12 + orb.energy * 0.88) * (0.35 + 0.65 * jitter)
                    x: f * (wave.width - width); anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(1.5, wave.width / wave.bars * 0.45); radius: width / 2
                    height: Math.max(1.5, wave.height * amp)
                    color: orb.wordColour
                    opacity: 0.55 + 0.45 * bell
                }
            }
        }
    }
    Accessible.role: Accessible.Graphic
    Accessible.name: "APVIS core: " + word
}
