import QtQuick
import "../theme"

// "Awakening" (owner concept, screen 04): when Home starts, the APVIS mark
// lights up inside its smoke, then the desktop fades in. About three seconds;
// shorter with Reduce motion. Click or press a key to skip.
Item {
    id: intro
    property bool still: false
    property bool active: true
    signal finished()
    visible: active || opacity > 0.01
    opacity: active ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 700; easing.type: Easing.InOutCubic } }
    property real t: 0                          // 0..1 over the sequence
    NumberAnimation on t {
        running: intro.active
        from: 0; to: 1; duration: intro.still ? 900 : 3000; easing.type: Easing.Linear
        onFinished: intro.finish()
    }
    function finish() { if (active) { active = false; finished() } }
    function ease(a, b) { return Math.max(0, Math.min(1, (t - a) / (b - a))) }

    Rectangle { anchors.fill: parent; color: Theme.ink }
    MouseArea { anchors.fill: parent; enabled: intro.active; onClicked: intro.finish() }
    Keys.onPressed: event => { intro.finish(); event.accepted = false }

    Item {
        anchors.centerIn: parent
        width: Math.min(parent.width, parent.height) * 0.62; height: width
        Image {
            anchors.fill: parent; visible: Theme.coreStyle === "smoke"; source: Theme.artDir ? Theme.artDir + "core-smoke-back.png" : "../art/core-smoke-back.png"; smooth: true; mipmap: true
            opacity: intro.ease(0.05, 0.5) * 0.9
            rotation: intro.t * 50
            scale: 0.85 + 0.2 * intro.ease(0, 0.8)
        }
        Image {
            anchors.fill: parent; visible: Theme.coreStyle === "smoke"; source: Theme.artDir ? Theme.artDir + "core-smoke-mid.png" : "../art/core-smoke-mid.png"; smooth: true; mipmap: true
            opacity: intro.ease(0.15, 0.6) * 0.8
            rotation: -intro.t * 70 + 30
            scale: 0.8 + 0.2 * intro.ease(0.1, 0.9)
        }
        ApvisMark {
            anchors.centerIn: parent           // just the mark (owner)
            width: parent.width * 0.2; height: width * 0.88
            opacity: intro.ease(0.1, 0.4)
            scale: 0.85 + 0.15 * intro.ease(0.1, 0.55)
            glow: 0.4 + 1.2 * intro.ease(0.2, 0.7)
        }
    }

}
