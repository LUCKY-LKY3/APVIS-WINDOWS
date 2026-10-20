import QtQuick
import QtQuick3D
import "../theme"

// The JARVIS core (owner's reference images, 2026-10-20): a geodesic wire globe in
// glinting particles, a ring of segmented blocks and a ragged particle halo. One
// shader (jarvis.frag) draws it over a square around the core, so the CPU only steps
// the time; the View3D re-renders when the Nucleus clock ticks.
Item {
    id: core
    property real time: 0
    property string mode: "idle"                 // idle | thinking | answering | attention
    property bool still: false
    property real centreOpacity: 1
    property real energy: mode === "thinking" ? 1.0 : mode === "answering" ? 0.6 : mode === "attention" ? 0.45 : 0.08
    Behavior on energy { NumberAnimation { duration: 900; easing.type: Easing.InOutSine } }
    readonly property real outer: Math.min(width, height) * 0.44
    readonly property real extent: 1.12
    readonly property real half: outer * extent

    View3D {
        x: core.width / 2 - core.half
        y: core.height / 2 - core.half
        width: Math.max(2, Math.round(core.half * 2))
        height: width
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Transparent
            antialiasingMode: SceneEnvironment.NoAA
        }
        OrthographicCamera { z: 100 }
        Model {
            source: "#Rectangle"
            materials: CustomMaterial {
                shadingMode: CustomMaterial.Unshaded
                sourceBlend: CustomMaterial.One
                destinationBlend: CustomMaterial.OneMinusSrcAlpha
                depthDrawMode: Material.NeverDepthDraw
                cullMode: Material.NoCulling
                vertexShader: "jarvis.vert"
                fragmentShader: "jarvis.frag"
                property real uTime: core.still ? 4.0 : core.time
                property real uEnergy: core.energy
                property real uExtent: core.extent
                property real uStrength: 1.0
                property color uTint: Theme.coreTint
                property color uHi: Theme.coreHighlight
            }
        }
    }
}
