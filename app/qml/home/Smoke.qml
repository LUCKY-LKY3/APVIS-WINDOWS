import QtQuick
import QtQuick3D
import "../theme"

// GPU smoke around the Nucleus (Full tier only; lower tiers and Safe Graphics
// keep the cached Atmosphere, which also supplies the haze across the room).
//
// Cost control, measured on the OptiPlex HD 4600 at 1080p (dev.18: a
// full-screen half-resolution pass held Home at ~27 fps):
//  - only a square around the core is drawn, not the whole screen;
//  - at a third of the resolution, scaled up (smoke is soft);
//  - its time advances in 20 Hz steps, so the View3D re-renders 20 times a
//    second and the scene graph reuses its texture in between.
Item {
    id: smoke
    property real time: 0
    property point center: Qt.point(0.5, 0.5)   // Nucleus centre, 0..1 of this item
    property real radius: 0.3                   // sphere radius as a fraction of this item's height
    property bool front: false
    property real strength: 1.0
    property real reach: front ? 1.35 : 1.9     // region half-size, in sphere radii
    property int downscale: 3
    readonly property real half: Math.max(8, radius * height * reach)
    readonly property real stepTime: Math.floor(time * 20) / 20

    View3D {
        x: smoke.center.x * smoke.width - smoke.half
        y: smoke.center.y * smoke.height - smoke.half
        width: Math.max(2, Math.round(smoke.half * 2 / smoke.downscale))
        height: width
        scale: smoke.downscale
        transformOrigin: Item.TopLeft
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
                vertexShader: "smoke.vert"
                fragmentShader: "smoke.frag"
                property real uTime: smoke.stepTime
                // The region's height as a fraction of the screen's: keeps the
                // noise the same size as when the smoke covered the screen.
                property real uSpan: smoke.half * 2 / Math.max(1, smoke.height)
                property real uRadius: smoke.radius
                property real uFront: smoke.front ? 1.0 : 0.0
                property real uStrength: smoke.strength
                property color uTint: Theme.accentSoft
                property color uGlow: Theme.glow
                property color uSilver: Theme.text
            }
        }
    }
}
