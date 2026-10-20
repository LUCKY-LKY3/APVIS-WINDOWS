import QtQuick
import QtQuick3D
import "../theme"

// The globe's land, grid, night and shading drawn by one shader (globe.frag) so the Intelligence globe can
// turn at the display's refresh rate in APVIS for Windows; AtlasGlobe's Canvas then only draws what moves.
Item {
    id: base
    property real lon0: 0
    property real lat0: 0
    property real radius: 100
    property point centre: Qt.point(0, 0)
    property var sun: [0, 0, 1]
    property bool night: true

    View3D {
        x: base.centre.x - base.radius
        y: base.centre.y - base.radius
        width: Math.max(2, Math.round(base.radius * 2))
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
                vertexShader: "../home/jarvis.vert"
                fragmentShader: "globe.frag"
                property real uLon0: base.lon0
                property real uLat0: base.lat0
                property real uExtent: 1.0
                property real uNightOn: base.night ? 1.0 : 0.0
                property vector3d uSun: Qt.vector3d(base.sun[0], base.sun[1], base.sun[2])
                property color uAccent: Theme.accent
                property color uText: Theme.text
                property color uNight: Theme.globeNight
                property color uWarm: Theme.warm
                property color uSheen: Theme.sheenBase
                property color uShade: Theme.shadeBase
                property TextureInput uLand: TextureInput {
                    texture: Texture { source: "../art/world-mask.png"; generateMipmaps: true; mipFilter: Texture.Linear }
                }
            }
        }
    }
}
