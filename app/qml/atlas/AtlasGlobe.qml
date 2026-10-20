import QtQuick
import "../theme"

// The Atlas globe: the Earth as an atlas — continents and country borders
// (Natural Earth), oceans and major cities labelled, shaded as a sphere and
// lit by the sun's real position now (night side dark, city lights on) —
// with the live events from the public feeds. Drag to turn it, scroll to zoom, click an event to select it,
// double-click to open the detailed map there. It turns slowly on its own
// unless motion is reduced or the owner is using it.
Item {
    id: globe
    property var dots: []                 // (unused by the atlas look; kept for the API)
    property string landJson: "{}"        // world-land.json: rings [lon, lat, ...]
    property string bordersJson: "{}"     // world-borders.json: lines [lon, lat, ...]
    property var feeds: ({})              // { quakes: [...], alerts: [...], events: [...], iss: [...] } (already filtered by layer)
    property var issTrail: []
    property var satTrack: []             // [[lat, lon, alt], ...] one orbit of the chosen satellite
    // Satellite colours by kind (OSIRIS-style: navigation green, comms/geo cyan, debris red).
    readonly property var satColours: Theme.satColours
    property var selected: null           // { kind, id }
    property bool night: true
    property bool still: false
    property real lon0: -5                // centre of the view (Europe first)
    property real lat0: 24
    property real zoom: 1
    signal picked(string kind, var item)
    signal openMap(real lat, real lon)
    signal pointed(string where)

    readonly property real radius: Math.min(width, height) * 0.42 * zoom
    readonly property real cx: width / 2
    readonly property real cy: height / 2
    property real phase: 0
    property real idleUntil: 0
    property var hits: []
    property var sunNow: [0, 0, 1]

    Behavior on zoom { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
    Behavior on lon0 { enabled: turnTo.running; NumberAnimation { duration: 900; easing.type: Easing.InOutCubic } }
    Behavior on lat0 { enabled: turnTo.running; NumberAnimation { duration: 900; easing.type: Easing.InOutCubic } }
    Timer { id: turnTo; interval: 950 }
    function focusOn(lat, lon) {
        let target = lon
        while (target - lon0 > 180) target -= 360
        while (target - lon0 < -180) target += 360
        idleUntil = Date.now() + 15000
        turnTo.restart()
        lon0 = target; lat0 = Math.max(-60, Math.min(60, lat))
    }

    // Unit vectors for coastlines and borders, computed once.
    function toUnit(list) {
        const u = []
        for (let i = 0; i + 1 < list.length; i += 2) {
            const lo = list[i] * Math.PI / 180, la = list[i + 1] * Math.PI / 180
            u.push(Math.cos(la) * Math.sin(lo), Math.sin(la), Math.cos(la) * Math.cos(lo))
        }
        return u
    }
    property var landUnits: []
    property var borderUnits: []
    onLandJsonChanged: { landUnits = (JSON.parse(landJson || "{}").rings || []).map(r => toUnit(r)); art.requestPaint() }
    onBordersJsonChanged: { borderUnits = (JSON.parse(bordersJson || "{}").lines || []).map(r => toUnit(r)); art.requestPaint() }
    // Places to name (well-known coordinates).
    readonly property var oceans: [["PACIFIC OCEAN", 0, -160], ["PACIFIC OCEAN", 5, 165], ["ATLANTIC OCEAN", 15, -40], ["ATLANTIC OCEAN", -20, -15],
                                   ["INDIAN OCEAN", -20, 80], ["ARCTIC OCEAN", 82, 0], ["SOUTHERN OCEAN", -62, 60]]
    readonly property var cities: [["London", 51.51, -0.13], ["New York", 40.71, -74.0], ["Los Angeles", 34.05, -118.24], ["Mexico City", 19.43, -99.13],
                                   ["São Paulo", -23.55, -46.63], ["Buenos Aires", -34.6, -58.38], ["Paris", 48.86, 2.35], ["Madrid", 40.42, -3.7],
                                   ["Berlin", 52.52, 13.4], ["Rome", 41.9, 12.5], ["Moscow", 55.76, 37.62], ["Istanbul", 41.01, 28.98],
                                   ["Cairo", 30.04, 31.24], ["Lagos", 6.52, 3.38], ["Nairobi", -1.29, 36.82], ["Johannesburg", -26.2, 28.05],
                                   ["Dubai", 25.2, 55.27], ["Delhi", 28.61, 77.21], ["Mumbai", 19.08, 72.88], ["Beijing", 39.9, 116.4],
                                   ["Shanghai", 31.23, 121.47], ["Tokyo", 35.68, 139.69], ["Seoul", 37.57, 126.98], ["Singapore", 1.35, 103.82],
                                   ["Jakarta", -6.2, 106.85], ["Sydney", -33.87, 151.21], ["Toronto", 43.65, -79.38], ["Chicago", 41.88, -87.63],
                                   ["Lima", -12.05, -77.04], ["Bangkok", 13.76, 100.5]]
    onFeedsChanged: art.requestPaint()
    onSelectedChanged: art.requestPaint()
    onZoomChanged: { frame.requestPaint(); art.requestPaint() }
    onWidthChanged: { frame.requestPaint(); art.requestPaint() }
    onHeightChanged: { frame.requestPaint(); art.requestPaint() }
    onLon0Changed: art.requestPaint()
    onLat0Changed: art.requestPaint()

    // APVIS for Windows: turn at the display's refresh rate (60/144 Hz) instead of the OptiPlex's ~25 fps.
    property bool smooth: false
    FrameAnimation {
        running: globe.visible && !globe.still && globe.smooth
        onTriggered: {
            const dt = Math.min(0.1, frameTime)
            globe.phase = (globe.phase + 0.45 * dt) % 1
            if (!drag.pressed && Date.now() > globe.idleUntil && !turnTo.running) globe.lon0 = (globe.lon0 + 3 * dt) % 360
            art.requestPaint()
        }
    }
    // ~25 fps turning and pulsing while visible (paused while dragging, after a pick, or with Reduce motion).
    Timer {
        interval: 40; repeat: true
        running: globe.visible && !globe.still && !globe.smooth
        onTriggered: {
            globe.phase = (globe.phase + 0.018) % 1
            if (!drag.pressed && Date.now() > globe.idleUntil && !turnTo.running) globe.lon0 = (globe.lon0 + 0.12) % 360
            art.requestPaint()
        }
    }

    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
    function sun() {
        const d = new Date()
        const day = (Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - Date.UTC(d.getUTCFullYear(), 0, 0)) / 864e5
        const decl = -23.44 * Math.cos(2 * Math.PI / 365 * (day + 10)) * Math.PI / 180
        const sunLon = -(d.getUTCHours() + d.getUTCMinutes() / 60 - 12) * 15 * Math.PI / 180
        return [Math.cos(decl) * Math.sin(sunLon), Math.sin(decl), Math.cos(decl) * Math.cos(sunLon)]
    }
    // World → screen: [x, y, depth] (depth > 0 faces the viewer).
    function project(lat, lon) {
        const la = lat * Math.PI / 180, lo = lon * Math.PI / 180
        return projectUnit(Math.cos(la) * Math.sin(lo), Math.sin(la), Math.cos(la) * Math.cos(lo))
    }
    function projectUnit(x, y, z) {
        const a = lon0 * Math.PI / 180, p = lat0 * Math.PI / 180
        const ca = Math.cos(a), sa = Math.sin(a), cp = Math.cos(p), sp = Math.sin(p)
        const x1 = x * ca - z * sa, z1 = z * ca + x * sa
        const y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp
        return [cx + radius * x1, cy - radius * y2, z2]
    }
    function unproject(sx, sy) {
        const x1 = (sx - cx) / radius, y2 = (cy - sy) / radius, rr = x1 * x1 + y2 * y2
        if (rr > 1) return null
        const z2 = Math.sqrt(1 - rr)
        const a = lon0 * Math.PI / 180, p = lat0 * Math.PI / 180
        const y = y2 * Math.cos(p) + z2 * Math.sin(p), z1 = -y2 * Math.sin(p) + z2 * Math.cos(p)
        const x = x1 * Math.cos(a) + z1 * Math.sin(a), z = -x1 * Math.sin(a) + z1 * Math.cos(a)
        let lon = Math.atan2(x, z) * 180 / Math.PI
        return [Math.asin(Math.max(-1, Math.min(1, y))) * 180 / Math.PI, lon]
    }

    // Static: atmosphere halo and the ocean disk (repainted only on resize/zoom).
    Canvas {
        id: frame
        anchors.fill: parent
        Component.onCompleted: requestPaint()
        onPaint: {
            const c = getContext("2d"), R = globe.radius, x = globe.cx, y = globe.cy
            c.reset(); c.clearRect(0, 0, width, height)
            const halo = c.createRadialGradient(x, y, R * 0.92, x, y, R * 1.35)
            halo.addColorStop(0, globe.rgba(Theme.accent, 0.32)); halo.addColorStop(0.25, globe.rgba(Theme.accent, 0.12))
            halo.addColorStop(1, globe.rgba(Theme.accent, 0))
            c.fillStyle = halo; c.fillRect(x - R * 1.4, y - R * 1.4, R * 2.8, R * 2.8)
            const sea = c.createRadialGradient(x - R * 0.35, y - R * 0.4, R * 0.05, x, y, R)
            sea.addColorStop(0, Theme.css(Theme.seaShallow, 1)); sea.addColorStop(0.55, Theme.css(Theme.seaMid, 1)); sea.addColorStop(1, Theme.css(Theme.seaDeep, 1))
            c.fillStyle = sea; c.beginPath(); c.arc(x, y, R, 0, Math.PI * 2); c.fill()
            c.strokeStyle = globe.rgba(Theme.accent, 0.75); c.lineWidth = 1.4
            c.beginPath(); c.arc(x, y, R, 0, Math.PI * 2); c.stroke()
            c.strokeStyle = globe.rgba(Theme.accent, 0.15); c.lineWidth = 6
            c.beginPath(); c.arc(x, y, R + 3, 0, Math.PI * 2); c.stroke()
            // Outer HUD ring with ticks.
            c.strokeStyle = globe.rgba(Theme.accent, 0.25); c.lineWidth = 1
            c.beginPath(); c.arc(x, y, R * 1.12, 0, Math.PI * 2); c.stroke()
            for (let i = 0; i < 120; ++i) {
                const a = i / 120 * Math.PI * 2, major = i % 10 === 0
                c.strokeStyle = globe.rgba(Theme.accent, major ? 0.55 : 0.2)
                c.beginPath(); c.moveTo(x + Math.cos(a) * R * 1.12, y + Math.sin(a) * R * 1.12)
                c.lineTo(x + Math.cos(a) * (R * 1.12 + (major ? 9 : 4)), y + Math.sin(a) * (R * 1.12 + (major ? 9 : 4))); c.stroke()
            }
        }
    }

    // APVIS for Windows: land, grid, night and shading on the GPU (the Canvas below then skips them).
    readonly property bool gpu: smooth
    GlobeBase {
        anchors.fill: parent
        visible: globe.gpu
        lon0: globe.lon0; lat0: globe.lat0
        radius: globe.radius; centre: Qt.point(globe.cx, globe.cy)
        sun: globe.sunNow; night: globe.night
    }
    // Dynamic: graticule, land, events.
    Canvas {
        id: art
        anchors.fill: parent
        renderStrategy: Canvas.Cooperative
        onPaint: {
            const c = getContext("2d"), R = globe.radius
            c.reset(); c.clearRect(0, 0, width, height)
            if (R < 10) return
            // Graticule (front half only).
            if (!globe.gpu) {
            c.strokeStyle = globe.rgba(Theme.accent, 0.13); c.lineWidth = 0.8
            c.beginPath()
            for (let lo = -180; lo < 180; lo += 30) {
                let pen = false
                for (let la = -90; la <= 90; la += 5) {
                    const p = globe.project(la, lo)
                    if (p[2] > 0) { pen ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]); pen = true } else pen = false
                }
            }
            for (let la = -60; la <= 60; la += 30) {
                let pen = false
                for (let lo = -180; lo <= 180; lo += 5) {
                    const p = globe.project(la, lo)
                    if (p[2] > 0) { pen ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]); pen = true } else pen = false
                }
            }
            c.stroke()
            }
            // Continents: projected coastline rings; the far side folds onto the limb.
            const a = globe.lon0 * Math.PI / 180, p = globe.lat0 * Math.PI / 180
            const ca = Math.cos(a), sa = Math.sin(a), cp = Math.cos(p), sp = Math.sin(p)
            const P = (x, y, z) => { const x1 = x * ca - z * sa, z1 = z * ca + x * sa
                                     return [x1, y * cp - z1 * sp, y * sp + z1 * cp] }
            const cx0 = globe.cx, cy0 = globe.cy
            if (!globe.gpu) {
            c.beginPath()
            for (const ring of globe.landUnits) {
                let any = false
                const pts = []
                for (let i = 0; i + 2 < ring.length; i += 3) {
                    const q = P(ring[i], ring[i + 1], ring[i + 2])
                    if (q[2] > 0) any = true
                    if (q[2] < 0) { const l = Math.sqrt(q[0] * q[0] + q[1] * q[1]) || 1; q[0] /= l; q[1] /= l }
                    pts.push(cx0 + R * q[0], cy0 - R * q[1])
                }
                if (!any) continue
                c.moveTo(pts[0], pts[1])
                for (let i = 2; i < pts.length; i += 2) c.lineTo(pts[i], pts[i + 1])
                c.closePath()
            }
            const landFill = c.createRadialGradient(cx0 - R * 0.35, cy0 - R * 0.4, R * 0.1, cx0, cy0, R)
            landFill.addColorStop(0, globe.rgba(Theme.accent, 0.62)); landFill.addColorStop(1, globe.rgba(Theme.accent, 0.34))
            c.fillStyle = landFill; c.fill()
            c.strokeStyle = globe.rgba(Theme.accent, 0.22); c.lineWidth = 4; c.stroke()
            c.strokeStyle = globe.rgba(Theme.text, 0.75); c.lineWidth = 0.9; c.stroke()
            // Country borders (front side only).
            c.strokeStyle = globe.rgba(Theme.text, 0.28); c.lineWidth = 0.7
            c.beginPath()
            for (const line of globe.borderUnits) {
                let pen = false
                for (let i = 0; i + 2 < line.length; i += 3) {
                    const q = P(line[i], line[i + 1], line[i + 2])
                    if (q[2] > 0.02) { pen ? c.lineTo(cx0 + R * q[0], cy0 - R * q[1]) : c.moveTo(cx0 + R * q[0], cy0 - R * q[1]); pen = true }
                    else pen = false
                }
            }
            c.stroke()
            }
            // Night: the half of the sphere facing away from the sun, bounded by
            // the terminator (a great circle, drawn exactly).
            if (globe.night && !globe.gpu) {
                const S = globe.sun()
                const s2 = P(S[0], S[1], S[2])
                // Two unit vectors across the terminator circle.
                let u1 = Math.abs(S[1]) < 0.9 ? [S[2], 0, -S[0]] : [0, S[2], -S[1]]
                let l1 = Math.hypot(u1[0], u1[1], u1[2]); u1 = [u1[0] / l1, u1[1] / l1, u1[2] / l1]
                const u2 = [S[1] * u1[2] - S[2] * u1[1], S[2] * u1[0] - S[0] * u1[2], S[0] * u1[1] - S[1] * u1[0]]
                const ring = []
                for (let k = 0; k < 180; ++k) {
                    const t = k / 180 * Math.PI * 2, ct = Math.cos(t), st = Math.sin(t)
                    ring.push(P(u1[0] * ct + u2[0] * st, u1[1] * ct + u2[1] * st, u1[2] * ct + u2[2] * st))
                }
                // Front arc of the terminator, in order, starting just after a back point.
                let startAt = ring.findIndex((q, i) => q[2] >= 0 && ring[(i + 179) % 180][2] < 0)
                c.beginPath()
                if (startAt < 0) {
                    // Whole terminator on one side: all night or all day in view.
                    if (s2[2] < 0) { c.arc(cx0, cy0, R, 0, Math.PI * 2) }
                } else {
                    const front = []
                    for (let k = 0; k < 180; ++k) { const q = ring[(startAt + k) % 180]; if (q[2] < 0) break; front.push(q) }
                    c.moveTo(cx0 + R * front[0][0], cy0 - R * front[0][1])
                    for (const q of front) c.lineTo(cx0 + R * q[0], cy0 - R * q[1])
                    // Close along the limb on the side away from the sun.
                    const aEnd = Math.atan2(-front[front.length - 1][1], front[front.length - 1][0])
                    const aStart = Math.atan2(-front[0][1], front[0][0])
                    const night = Math.atan2(s2[1], -s2[0])       // screen angle pointing away from the sun
                    const norm = v => { while (v < 0) v += Math.PI * 2; while (v >= Math.PI * 2) v -= Math.PI * 2; return v }
                    const cwMid = norm(aEnd + norm(aStart - aEnd) / 2)
                    const diff = Math.abs(((cwMid - norm(night)) + 3 * Math.PI) % (Math.PI * 2) - Math.PI)
                    c.arc(cx0, cy0, R, aEnd, aStart, diff > Math.PI / 2)
                    c.closePath()
                }
                c.fillStyle = Theme.css(Theme.globeNight, 0.58); c.fill()
                // Twilight line.
                c.strokeStyle = Theme.css(Theme.warm, 0.35); c.lineWidth = 1.2
                c.beginPath()
                let pen = false
                for (const q of ring) { if (q[2] > 0) { pen ? c.lineTo(cx0 + R * q[0], cy0 - R * q[1]) : c.moveTo(cx0 + R * q[0], cy0 - R * q[1]); pen = true } else pen = false }
                c.stroke()
                globe.sunNow = S
            } else if (globe.night) globe.sunNow = globe.sun()
            if (!globe.gpu) {
            // Sphere shading: a highlight up-left and the limb darkening.
            const hi = c.createRadialGradient(cx0 - R * 0.4, cy0 - R * 0.45, 0, cx0 - R * 0.4, cy0 - R * 0.45, R * 0.9)
            hi.addColorStop(0, Theme.css(Theme.sheenBase, 0.08)); hi.addColorStop(1, Theme.css(Theme.sheenBase, 0))
            c.fillStyle = hi; c.beginPath(); c.arc(cx0, cy0, R, 0, Math.PI * 2); c.fill()
            const limb = c.createRadialGradient(cx0, cy0, R * 0.62, cx0, cy0, R)
            limb.addColorStop(0, Theme.css(Theme.shadeBase, 0)); limb.addColorStop(1, Theme.css(Theme.shadeBase, 0.5))
            c.fillStyle = limb; c.fill()
            }
            // Oceans and cities.
            c.textAlign = "center"
            c.font = "italic " + Math.max(9, R * 0.028) + "px sans-serif"
            for (const o of globe.oceans) {
                const q = globe.project(o[1], o[2]); if (q[2] < 0.35) continue
                c.fillStyle = globe.rgba(Theme.text, 0.35 * Math.min(1, (q[2] - 0.35) * 3)); c.fillText(o[0], q[0], q[1])
            }
            c.textAlign = "left"; c.font = Math.max(9, R * 0.026) + "px sans-serif"
            const S2 = globe.night ? globe.sunNow : null
            for (const city of globe.cities) {
                const la = city[1] * Math.PI / 180, lo = city[2] * Math.PI / 180
                const wx = Math.cos(la) * Math.sin(lo), wy = Math.sin(la), wz = Math.cos(la) * Math.cos(lo)
                const q = P(wx, wy, wz); if (q[2] < 0.2) continue
                const x = cx0 + R * q[0], y = cy0 - R * q[1], fade = Math.min(1, (q[2] - 0.2) * 3)
                const dark = S2 && wx * S2[0] + wy * S2[1] + wz * S2[2] < -0.05
                if (dark) {             // city lights on the night side
                    const g = c.createRadialGradient(x, y, 0, x, y, 7)
                    g.addColorStop(0, Theme.css(Theme.sunlight, 0.7 * fade)); g.addColorStop(1, Theme.css(Theme.sunlight, 0))
                    c.fillStyle = g; c.fillRect(x - 7, y - 7, 14, 14)
                }
                c.fillStyle = dark ? Theme.css(Theme.starlight, fade) : globe.rgba(Theme.text, fade)
                c.beginPath(); c.arc(x, y, 1.8, 0, Math.PI * 2); c.fill()
                if (R > 220) { c.fillStyle = globe.rgba(Theme.text, 0.7 * fade); c.fillText(city[0], x + 5, y - 3) }
            }
            // Events.
            const s = Math.max(1.6, R / 125)
            const hits = []
            const sel = globe.selected
            const glow = (x, y, r, col, al) => { const g = c.createRadialGradient(x, y, 0, x, y, r)
                g.addColorStop(0, globe.rgba(col, al)); g.addColorStop(1, globe.rgba(col, 0)); c.fillStyle = g; c.fillRect(x - r, y - r, 2 * r, 2 * r) }
            const ring = (x, y, r) => { c.strokeStyle = globe.rgba(Theme.text, 1); c.lineWidth = 1.4; c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.stroke() }
            const f = globe.feeds || {}
            // Satellites (after OSIRIS): each at a height that grows with its real altitude on a log scale, so low
            // orbits hug the globe and the geostationary belt makes a ring; hidden where the globe is in front.
            const sats = f.satellites || []
            if (sats.length) {
                const ka = globe.lon0 * Math.PI / 180, kp = globe.lat0 * Math.PI / 180
                const cka = Math.cos(ka), ska = Math.sin(ka), ckp = Math.cos(kp), skp = Math.sin(kp)
                const tone = {}
                for (const k in globe.satColours) tone[k] = globe.rgba(Qt.color(globe.satColours[k]), 0.85)
                const dim = globe.rgba(Qt.color(globe.satColours.other), 0.6)
                for (const sat of sats) {
                    const la = sat.lat * Math.PI / 180, lo = sat.lon * Math.PI / 180
                    const h = 1 + 0.035 * Math.log2(1 + Math.max(0, sat.alt || 0) / 200)
                    const x = Math.cos(la) * Math.sin(lo) * h, y = Math.sin(la) * h, z = Math.cos(la) * Math.cos(lo) * h
                    const x1 = x * cka - z * ska, z1 = z * cka + x * ska
                    const y2 = y * ckp - z1 * skp, z2 = y * skp + z1 * ckp
                    if (z2 < 0 && x1 * x1 + y2 * y2 < 1) continue          // behind the globe
                    const sx = globe.cx + R * x1, sy = globe.cy - R * y2
                    const k = sat.k || sat.kind || "other"
                    c.fillStyle = tone[k] || dim
                    const big = k === "station" || k === "bright"
                    c.fillRect(sx - (big ? 1.5 : 1), sy - (big ? 1.5 : 1), big ? 3 : 2, big ? 3 : 2)
                    hits.push([sx, sy, "satellites", sat])
                    if (sel && sel.kind === "satellites" && sel.id === sat.id) ring(sx, sy, 9)
                }
            }
            for (const i of (f.events || [])) {
                const q = globe.project(i.lat, i.lon); if (q[2] <= 0) continue
                const col = Qt.color(i.kind === "fire" ? Theme.eventColours.fire : i.kind === "storm" ? Theme.eventColours.storm : i.kind === "volcano" ? Theme.eventColours.volcano : Theme.muted)
                c.fillStyle = globe.rgba(col, 0.9); c.beginPath(); c.arc(q[0], q[1], 2.2 * s / 1.4, 0, Math.PI * 2); c.fill()
                hits.push([q[0], q[1], "events", i])
                if (sel && sel.kind === "events" && sel.id === i.id) ring(q[0], q[1], 10)
            }
            for (const i of (f.alerts || [])) {
                if (i.alert === "Green") continue
                const q = globe.project(i.lat, i.lon); if (q[2] <= 0) continue
                const col = Qt.color(i.alert === "Red" ? Theme.critical : Theme.warm)
                glow(q[0], q[1], 16, col, 0.35)
                c.strokeStyle = globe.rgba(col, 0.95); c.lineWidth = 1.5; c.beginPath(); c.arc(q[0], q[1], 6, 0, Math.PI * 2); c.stroke()
                hits.push([q[0], q[1], "alerts", i])
                if (sel && sel.kind === "alerts" && sel.id === i.id) ring(q[0], q[1], 13)
            }
            for (const i of (f.quakes || [])) {
                const q = globe.project(i.lat, i.lon); if (q[2] <= 0) continue
                const r = 1.8 + Math.pow(Math.max(0, i.mag - 2), 1.35) * 1.5, col = Qt.color(i.mag >= 6 ? Theme.critical : Theme.warm)
                glow(q[0], q[1], r * 3.2, col, 0.4)
                c.fillStyle = globe.rgba(col, 0.9); c.beginPath(); c.arc(q[0], q[1], r, 0, Math.PI * 2); c.fill()
                if (Date.now() - i.time_ms < 3 * 3600e3 && !globe.still)
                    for (const off of [0, 0.5]) { const t = (globe.phase + off) % 1
                        c.strokeStyle = globe.rgba(col, 0.7 * (1 - t)); c.lineWidth = 1.3; c.beginPath(); c.arc(q[0], q[1], r + t * 20, 0, Math.PI * 2); c.stroke() }
                hits.push([q[0], q[1], "quakes", i])
                if (sel && sel.kind === "quakes" && sel.id === i.id) ring(q[0], q[1], r + 8)
            }
            // The chosen satellite's orbit (one period).
            if (globe.satTrack.length > 1) {
                c.strokeStyle = globe.rgba(Qt.color(globe.satColours.geo), 0.7); c.lineWidth = 1.2
                c.beginPath()
                let pen = false
                for (const pt of globe.satTrack) {
                    const la = pt[0] * Math.PI / 180, lo = pt[1] * Math.PI / 180
                    const h = 1 + 0.035 * Math.log2(1 + Math.max(0, pt[2] || 0) / 200)
                    const q = globe.projectUnit(Math.cos(la) * Math.sin(lo) * h, Math.sin(la) * h, Math.cos(la) * Math.cos(lo) * h)
                    const ux = (q[0] - globe.cx) / R, uy = (q[1] - globe.cy) / R
                    if (q[2] < 0 && ux * ux + uy * uy < 1) { pen = false; continue }
                    pen ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]); pen = true
                }
                c.stroke()
            }
            // ISS: its recent track and the station.
            const t = globe.issTrail
            c.lineWidth = 1.4
            for (let k = 1; k < t.length; ++k) {
                const p0 = globe.project(t[k - 1][0], t[k - 1][1]), p1 = globe.project(t[k][0], t[k][1])
                if (p0[2] <= 0 || p1[2] <= 0) continue
                c.strokeStyle = globe.rgba(Theme.text, 0.6 * k / t.length); c.beginPath(); c.moveTo(p0[0], p0[1]); c.lineTo(p1[0], p1[1]); c.stroke()
            }
            const iss = (f.iss || [])[0]
            if (iss) {
                const q = globe.project(iss.lat, iss.lon)
                if (q[2] > 0) {
                    glow(q[0], q[1], 20, Qt.color(Theme.text), 0.35)
                    c.fillStyle = globe.rgba(Theme.text, 1); c.fillRect(q[0] - 2.5, q[1] - 2.5, 5, 5)
                    c.fillRect(q[0] - 11, q[1] - 2.5, 5, 5); c.fillRect(q[0] + 6, q[1] - 2.5, 5, 5)
                    c.font = "bold 10px monospace"; c.fillText("ISS", q[0] + 14, q[1] + 4)
                    hits.push([q[0], q[1], "iss", iss])
                    if (sel && sel.kind === "iss") ring(q[0], q[1], 16)
                }
            }
            // A light sweeping round the limb.
            if (!globe.still) {
                const ang = globe.phase * Math.PI * 2
                c.strokeStyle = globe.rgba(Theme.accent, 0.9); c.lineWidth = 2
                c.beginPath(); c.arc(globe.cx, globe.cy, R * 1.12, ang, ang + 0.5); c.stroke()
                c.strokeStyle = globe.rgba(Theme.accent, 0.25); c.lineWidth = 6
                c.beginPath(); c.arc(globe.cx, globe.cy, R * 1.12, ang, ang + 0.5); c.stroke()
            }
            globe.hits = hits
        }
    }

    MouseArea {
        id: drag
        anchors.fill: parent
        hoverEnabled: true
        property real lastX: 0
        property real lastY: 0
        property bool moved: false
        cursorShape: pressed && moved ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        onPressed: mouse => { lastX = mouse.x; lastY = mouse.y; moved = false; globe.idleUntil = Date.now() + 8000 }
        onPositionChanged: mouse => {
            const w = globe.unproject(mouse.x, mouse.y)
            globe.pointed(w ? Math.abs(w[0]).toFixed(2) + "°" + (w[0] >= 0 ? "N" : "S") + "  " + Math.abs(w[1]).toFixed(2) + "°" + (w[1] >= 0 ? "E" : "W") : "")
            if (!pressed) return
            const dx = mouse.x - lastX, dy = mouse.y - lastY
            if (Math.abs(dx) + Math.abs(dy) > 2) moved = true
            if (!moved) return
            const k = 180 / Math.PI / globe.radius
            globe.lon0 = globe.lon0 - dx * k
            globe.lat0 = Math.max(-70, Math.min(70, globe.lat0 + dy * k))
            lastX = mouse.x; lastY = mouse.y
            globe.idleUntil = Date.now() + 8000
        }
        onExited: globe.pointed("")
        onReleased: mouse => {
            if (moved) return
            let best = null, bestD = 16 * 16
            for (const h of globe.hits) {
                const d = (h[0] - mouse.x) * (h[0] - mouse.x) + (h[1] - mouse.y) * (h[1] - mouse.y)
                if (d < bestD) { bestD = d; best = h }
            }
            if (best) { globe.picked(best[2], best[3]); globe.focusOn(best[3].lat, best[3].lon) }
        }
        onDoubleClicked: mouse => { const w = globe.unproject(mouse.x, mouse.y); if (w) globe.openMap(w[0], w[1]) }
        onWheel: wheel => { globe.zoom = Math.max(0.6, Math.min(2.4, globe.zoom * (wheel.angleDelta.y > 0 ? 1.15 : 1 / 1.15))); globe.idleUntil = Date.now() + 8000 }
    }
}
