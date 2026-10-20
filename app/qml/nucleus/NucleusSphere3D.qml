import QtQuick
import "../theme"
import QtQuick3D
import ApvisNucleus

// GPU particle sphere (Full/Balanced). Requires a hardware scene graph; the
// Nucleus wrapper never loads this on the software backend.
View3D {
    id: view
    property int particles: 8000
    property real time: 0
    property real yaw: 0
    property real pitch: 0
    property real breath: 0
    property real turbulence: 0.1
    property real orbit: 0.16
    property real energy: 0.4
    property real globe: 0
    property real aperture: 0
    property real sizePx: 2.6
    property real clear: 0.30
    property color tint: Theme.coreTint
    property color warm: Theme.warm
    property color highlight: Theme.coreHighlight

    environment: SceneEnvironment {
        backgroundMode: SceneEnvironment.Transparent
        antialiasingMode: SceneEnvironment.NoAA
    }

    PerspectiveCamera {
        z: 600
        fieldOfView: 30
        clipNear: 10
        clipFar: 2000
    }

    Model {
        source: "#Rectangle"
        instancing: NucleusInstancing { count: view.particles }
        materials: CustomMaterial {
            shadingMode: CustomMaterial.Unshaded
            sourceBlend: CustomMaterial.One
            destinationBlend: CustomMaterial.One
            depthDrawMode: Material.NeverDepthDraw
            cullMode: Material.NoCulling
            vertexShader: "nucleus.vert"
            fragmentShader: "nucleus.frag"

            property real uTime: view.time
            property real uYaw: view.yaw
            property real uPitch: view.pitch
            property real uBreath: view.breath
            property real uTurbulence: view.turbulence
            property real uOrbit: view.orbit
            property real uEnergy: view.energy
            property real uGlobe: view.globe
            property real uAperture: view.aperture
            property real uSizePx: view.sizePx
            property real uClear: view.clear
            // Scene radius: the sphere fills ~72% of the view's half-height.
            property real uRadius: 0.72 * 600 * Math.tan(15 * Math.PI / 180)
            property size uViewport: Qt.size(Math.max(1, view.width), Math.max(1, view.height))
            property color uTint: view.tint
            property color uWarm: view.warm
            property color uHighlight: view.highlight
        }
    }
}
