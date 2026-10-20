import QtQuick
import "../theme"

// CPU particle Nucleus for Safe Graphics (software scene graph) and Minimal
// quality. Same shapes and maths as nucleus.vert, far fewer particles.
Canvas {
    id: canvas
    // JSON array of floats, 10 per particle:
    // [sx, sy, sz, gx, gy, gz, brightness, spark, ocean, seed]
    property string points: "[]"
    property real time: 0
    property real yaw: 0
    property real pitch: 0
    property real breath: 0
    property real turbulence: 0.1
    property real orbit: 0.16
    property real energy: 0.4
    property real globe: 0
    property real aperture: 0
    property real sizePx: 2.2
    property color tint: Theme.coreTint
    property color warm: Theme.warm
    renderStrategy: Canvas.Cooperative

    // Copied once into a flat typed array: reading the bridge list inside the
    // paint loop converts it on every access and made a frame take seconds.
    property var flat: new Float32Array(0)
    property int count: 0
    onPointsChanged: {
        let values = []
        try { values = JSON.parse(points) } catch (e) { values = [] }
        flat = new Float32Array(values)
        count = Math.floor(values.length / 10)
        requestPaint()
    }
    onTimeChanged: requestPaint()
    onGlobeChanged: requestPaint()
    onApertureChanged: requestPaint()

    onPaint: {
        const c = getContext("2d")
        c.reset()
        const cx = width / 2
        const cy = height / 2
        const radius = Math.min(width, height) * 0.36
        const cyaw = Math.cos(yaw), syaw = Math.sin(yaw)
        const cpitch = Math.cos(pitch), spitch = Math.sin(pitch)
        c.globalCompositeOperation = "lighter"
        const f = flat
        const n = count
        const t = time, orb = orbit, turb = turbulence, br = breath, gl = globe, ap = aperture
        for (let i = 0; i < n; ++i) {
            const o = i * 10
            const q = [f[o], f[o + 1], f[o + 2], f[o + 3], f[o + 4], f[o + 5], f[o + 6], f[o + 7], f[o + 8], f[o + 9]]
            const seed = q[9]
            // swirl + breathing + turbulence (sphere only)
            const a = t * orb * (seed - 0.5) * 0.8
            const ca = Math.cos(a), sa = Math.sin(a)
            let sx = q[0] * ca + q[2] * sa, sy = q[1], sz = -q[0] * sa + q[2] * ca
            const k = 1 + breath + Math.sin(time * (0.6 + seed * 1.4) + seed * 6.2831) * turbulence * 0.05
            sx *= k; sy *= k; sz *= k
            let x = sx + (q[3] * 1.02 - sx) * globe
            let y = sy + (q[4] * 1.02 - sy) * globe
            let z = sz + (q[5] * 1.02 - sz) * globe
            const x1 = x * cyaw + z * syaw, z1 = -x * syaw + z * cyaw
            const y2 = y * cpitch - z1 * spitch, z2 = y * spitch + z1 * cpitch
            x = x1; y = y2; z = z2
            const d = Math.sqrt(x * x + y * y)
            if (aperture > 0) {
                const ring = 1.10 + 0.24 * ((seed * 7.13) % 1)
                const target = Math.max(d, ring)
                const scale = d > 0.0001 ? (d + (target - d) * aperture) / d : 1
                x *= scale; y *= scale; z *= 1 - 0.8 * aperture
            }
            const clearR = 0.30 * (1 - globe) * (1 - aperture)
            const dc = Math.sqrt(x * x + y * y)
            if (dc < clearR) {
                const target = clearR + (dc / clearR) * 0.09
                if (dc > 0.0001) { x *= target / dc; y *= target / dc }
                else { x = target * Math.cos(seed * 6.2831); y = target * Math.sin(seed * 6.2831) }
            }
            const edge = Math.sqrt(x * x + y * y)
            const limb = 0.72 + 0.55 * Math.max(0, Math.min(1, (edge - 0.55) / 0.45))
            const depth = Math.max(0, Math.min(1, z * 0.5 + 0.5))
            let glow = q[6] * (0.30 + 0.70 * depth) * energy * limb
            if (q[8] > 0.5) glow *= 1 - 0.75 * globe
            const spark = q[7] > 0.5 && globe < 0.5
            const size = sizePx * (0.55 + 0.75 * depth) * (spark ? 1.6 : 1)
            c.globalAlpha = Math.min(1, glow)
            c.fillStyle = spark ? warm : tint
            c.fillRect(cx + x * radius - size / 2, cy - y * radius - size / 2, size, size)
        }
    }
}
