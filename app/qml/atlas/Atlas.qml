import QtQuick
import QtQuick.Controls
import "../theme"

// OSIRIS Atlas: the world, from public, key-free, sourced open data.
// Honesty rules (DESIGN-LANGUAGE / V2-06): every layer names its source and
// age; a layer that failed says so and draws nothing; trails are earlier
// reported positions, never predictions (between two updates a plane's icon coasts along its reported
// speed and heading for at most 30 s, and the panel says so); the day/night shadow is computed from
// the sun's position now; market prices are delayed and say so; only official
// public cameras. Aircraft load for the area on screen (the free sources answer
// within 250 NM of a point), so they appear once you zoom into a region.
Item {
    id: atlas
    property var info: ({ status: "off" })   // aircraft feed status (shell.atlas)
    property string aircraftJson: "[]"
    property string mapJson: "{}"            // UK coast + airports (detail when zoomed in)
    property string worldJson: "{}"          // OSINT layers (shell.atlasWorld)
    property string landJson: "{}"           // world land outlines
    property string dotsJson: "[]"           // land sample points for the dot-matrix world
    signal focusFlight(string callsign, string hexId)
    signal areaChanged(real lat, real lon)

    readonly property var map: JSON.parse(mapJson)
    readonly property var land: JSON.parse(landJson)
    readonly property var dots: JSON.parse(dotsJson)
    readonly property var world: JSON.parse(worldJson)
    readonly property var stats: info.stats || ({})
    readonly property bool live: info.status === "live"

    // ---- layers
    property var layersOn: ({ flights: true, quakes: true, events: true, alerts: true, iss: true, cameras: true, night: true })
    // "globe": the whole world at a glance (default); "map": the detailed, zoomable map.
    property string mode: "globe"
    property bool sideOpen: true             // the floating intel panel (INTEL button hides it)
    readonly property int entities: ["quakes", "events", "alerts", "cameras", "news"].reduce((n, k) => n + (feed(k).items || []).length, 0)
                                    + (flightsVisible ? planes.length : 0) + (feed("iss").items || []).length
    readonly property int layersActive: Object.keys(layersOn).filter(k => layersOn[k] !== false).length
    function toggle(key) { const o = Object.assign({}, layersOn); o[key] = !o[key]; layersOn = o }
    function feed(key) { return (world[key] || {}) }
    function items(key) { return layersOn[key] === false ? [] : (feed(key).items || []) }

    // ---- aircraft rows: [hex, callsign, reg, type, lat, lon, alt, ground, kt, track, age, emergency, vrate, typeName, trail]
    property var planes: []
    property var fromPos: ({})
    property real glide: 1
    property real planesAt: Date.now()       // when the current rows arrived
    // Where a plane's icon is drawn now: its reported position, coasting along the reported speed and
    // heading since the rows arrived (at most 30 s, V4 step 3), glided from where it was drawn before.
    function coast(p, ms) {
        if (p[7] || p[8] === null || p[9] === null || p[8] < 40) return [p[4], p[5]]
        const nm = p[8] * Math.min(30, Math.max(0, ms / 1000)) / 3600, tr = p[9] * Math.PI / 180
        return [p[4] + nm * Math.cos(tr) / 60, p[5] + nm * Math.sin(tr) / (60 * Math.max(0.2, Math.cos(p[4] * Math.PI / 180)))]
    }
    function drawnPos(p, nowMs) {
        const t = coast(p, nowMs - planesAt), f = fromPos[p[0]], g = glide
        return f ? [f[0] + (t[0] - f[0]) * g, f[1] + (t[1] - f[1]) * g] : t
    }
    onAircraftJsonChanged: {
        const previous = {}, nowMs = Date.now()
        for (const p of planes) previous[p[0]] = drawnPos(p, nowMs)
        fromPos = previous
        planes = JSON.parse(aircraftJson)
        planesAt = nowMs
        glideAnim.restart()
        overlay.requestPaint()
    }
    // Planes move between updates: repaint the flights more often the closer the map is zoomed in.
    Timer {
        interval: view.zoom >= 10 ? 100 : view.zoom >= 5 ? 250 : 1000
        repeat: true
        running: atlas.visible && atlas.mode === "map" && atlas.flightsVisible && !glideAnim.running
        onTriggered: { overlay.requestPaint(); atlas.followTick() }
    }
    // "Focus this flight": the map zooms onto the plane and keeps it in view (until you drag the map or
    // pick something else), and a photo of this airframe or its type comes from Wikimedia Commons.
    property string followHex: ""
    // The middle of the map you can see (the intel panel covers the right-hand side).
    property real lastAim: 0
    function aimAt(lat, lon, zoom) {
        lastAim = Date.now()                  // let the 500 ms glide finish before following again
        const z = Math.max(view.zoom, zoom), s = view.width / 360 * z
        const shift = sideOpen ? (side.width + 10) / 2 : 0
        flyTo(lat, lon + shift / s, zoom)
    }
    function focusPlane(p) {
        followHex = p[0]
        const pos = drawnPos(p, Date.now())
        aimAt(pos[0], pos[1], 48)
        shell.findPlanePhoto(p[0], p[2] || "", p[13] || "", p[3] || "")
        focusFlight(p[1], p[0])
    }
    function followTick() {
        if (!followHex || !selectedPlane || selectedPlane[0] !== followHex || Date.now() - lastAim < 900) return
        const pos = drawnPos(selectedPlane, Date.now()), x = view.px(pos[1]), y = view.py(pos[0])
        const cx = view.width / 2 - (sideOpen ? (side.width + 10) / 2 : 0)
        if (Math.abs(x - cx) > view.width * 0.15 || Math.abs(y - view.height / 2) > view.height * 0.2)
            aimAt(pos[0], pos[1], view.zoom)
    }
    readonly property var photo: selectedPlane && (shell.planePhoto || {}).hex === selectedPlane[0] ? shell.planePhoto : ({})
    NumberAnimation { id: glideAnim; target: atlas; property: "glide"; from: 0; to: 1; duration: 1100; easing.type: Easing.InOutCubic }
    onGlideChanged: overlay.requestPaint()
    onWorldJsonChanged: { issTrailAdd(); overlay.requestPaint() }
    onLayersOnChanged: { land_.requestPaint(); overlay.requestPaint() }
    readonly property bool flightsVisible: layersOn.flights && view.zoom >= 3
    readonly property var shownPlanes: flightsVisible ? planes.filter(p => passes(p)) : []

    property var issTrail: []
    function issTrailAdd() {
        const iss = (feed("iss").items || [])[0]
        if (!iss) return
        const t = issTrail.slice(-179)
        const last = t[t.length - 1]
        if (!last || last[0] !== iss.lat || last[1] !== iss.lon) t.push([iss.lat, iss.lon])
        issTrail = t
    }

    // ---- selection: { kind: "plane", hex } | { kind: layerKey, id }
    property var selected: null
    readonly property var selectedPlane: selected && selected.kind === "plane" ? planes.find(p => p[0] === selected.hex) || null : null
    readonly property var selectedItem: {
        if (!selected || selected.kind === "plane") return null
        return (feed(selected.kind).items || []).find(i => i.id === selected.id) || null
    }
    onSelectedChanged: {
        if (!selected || selected.kind !== "plane" || selected.hex !== followHex) followHex = ""
        overlay.requestPaint()
    }

    property string filterText: ""
    function passes(p) {
        if (!filterText) return true
        return (p[1] + " " + p[2] + " " + p[3] + " " + (p[13] || "") + " " + p[0]).toLowerCase().indexOf(filterText.toLowerCase()) >= 0
    }

    // ---- helpers
    property real now: Date.now()
    Timer { interval: 1000; repeat: true; running: atlas.visible; onTriggered: { atlas.now = Date.now(); land_.nightTick++ } }
    function nameOf(p) { return p[1] || p[2] || Theme.upper(p[0]) }
    function heightOf(p) { return p[7] ? "On the ground" : (p[6] === null ? "Altitude unknown" : p[6].toLocaleString(Qt.locale("en_GB"), "f", 0) + " ft") }
    function band(p) { return p[7] ? 0 : p[6] === null ? 2 : p[6] < 10000 ? 1 : p[6] < 25000 ? 2 : p[6] < 35000 ? 3 : 4 }
    readonly property var bandColours: [Theme.muted, Theme.signal, Theme.accent, Theme.bandHigh, Theme.text]
    function colourOf(p) { return p[11] ? Theme.attention : bandColours[band(p)] }
    function trend(p) { return p[12] === null || p[12] === undefined ? "" : p[12] > 300 ? "▲" : p[12] < -300 ? "▼" : "▶" }
    function ago(ms) {
        if (!ms || isNaN(ms)) return ""
        const s = Math.max(0, Math.round((now - ms) / 1000))
        return s < 90 ? s + " s ago" : s < 5400 ? Math.round(s / 60) + " min ago" : s < 172800 ? Math.round(s / 3600) + " h ago" : Math.round(s / 86400) + " days ago"
    }
    function whenOf(item) { return item.time_ms ? ago(item.time_ms) : item.time ? ago(Date.parse(item.time)) : "" }
    function alertColour(a) { return a === "Red" ? Theme.critical : a === "Orange" ? Theme.warm : Theme.accent }
    readonly property var kindColour: Theme.eventColours
    function colourOfItem(i) { return i.alert ? alertColour(i.alert) : i.mag !== undefined ? (i.mag >= 6 ? Theme.critical : Theme.warm) : (kindColour[i.kind] || Theme.muted) }
    function layerLine(key) {
        const l = feed(key)
        if (!l.status || l.status === "waiting") return "loading…"
        if (l.status !== "live") return l.error || "unavailable"
        return (l.items || []).length + " · " + (l.age_s === null || l.age_s === undefined ? "" : l.age_s < 90 ? l.age_s + " s" : Math.round(l.age_s / 60) + " min")
    }
    function fmtPrice(m) {
        const d = m.price >= 1000 ? 0 : m.price >= 10 ? 2 : 4
        return m.price.toLocaleString(Qt.locale("en_GB"), "f", d)
    }
    readonly property var quakes: feed("quakes").items || []
    readonly property var strongest: quakes.reduce((a, q) => !a || q.mag > a.mag ? q : a, null)
    readonly property int redOrange: (feed("alerts").items || []).filter(i => i.alert !== "Green").length
    readonly property int fires: (feed("events").items || []).filter(i => i.kind === "fire").length
    readonly property int storms: (feed("events").items || []).filter(i => i.kind === "storm").length + (feed("alerts").items || []).filter(i => i.kind === "cyclone").length
    readonly property var kp: (feed("space").items || [])[0]
    readonly property var feedKeys: ["quakes", "events", "alerts", "iss", "space", "cameras", "markets", "news"]
    readonly property int liveFeeds: feedKeys.filter(k => feed(k).status === "live").length
    readonly property bool still: !!(shell.render || {}).reducedMotion || !!(shell.render || {}).lite
    readonly property var marketRows: feed("markets").items || []
    readonly property int marketsUp: marketRows.filter(m => (m.change_pct || 0) >= 0).length
    property real reveal: 1
    onVisibleChanged: if (visible) entry.restart()
    NumberAnimation { id: entry; target: atlas; property: "reveal"; from: 0; to: 1; duration: 800; easing.type: Easing.OutCubic }
    readonly property var eventFeed: {
        const rows = []
        for (const i of items("alerts")) rows.push({ layer: "alerts", item: i, score: i.alert === "Red" ? 100 : i.alert === "Orange" ? 60 : 8 })
        for (const i of items("quakes")) rows.push({ layer: "quakes", item: i, score: i.mag * 10 })
        for (const i of items("events")) rows.push({ layer: "events", item: i, score: 20 })
        rows.sort((a, b) => b.score - a.score)
        return rows.slice(0, 150)
    }
    function flyTo(lat, lon, zoom) { view.cLat = Math.max(-75, Math.min(78, lat)); view.cLon = lon; view.zoom = Math.max(view.zoom, zoom) }
    function selectItem(layerKey, item) {
        selected = { kind: layerKey, id: item.id }
        if (item.lat === undefined) return
        if (mode === "globe" && layerKey !== "cameras") globeView.focusOn(item.lat, item.lon)
        else { mode = "map"; flyTo(item.lat, item.lon, layerKey === "cameras" ? 10 : 4) }
    }
    // Domain status for the Global Overview: [label, value, tone 0 calm / 1 notable / 2 severe, layer].
    function statusOf(k) { const l = feed(k); return l.status === "live" ? "" : l.status === "unavailable" ? "Offline" : "Loading…" }
    readonly property var overview: [
        ["Earthquakes", statusOf("quakes") || (strongest && strongest.mag >= 6 ? "M" + strongest.mag.toFixed(1) + " today" : quakes.length + " · normal"),
         strongest && strongest.mag >= 6 ? 1 : 0],
        ["Disasters", statusOf("alerts") || (redOrange ? redOrange + " severe" : "Normal"),
         (feed("alerts").items || []).some(i => i.alert === "Red") ? 2 : redOrange ? 1 : 0],
        ["Storms", statusOf("events") || (storms ? storms + " active" : "Calm"), storms > 5 ? 1 : 0],
        ["Wildfires", statusOf("events") || String(fires), fires > 40 ? 1 : 0],
        ["Space weather", statusOf("space") || (kp ? "Kp " + kp.kp.toFixed(1) + " · " + kp.level : "—"), kp && kp.kp >= 5 ? 1 : 0],
        ["Aviation", view.zoom >= 3 && mode === "map" ? (live ? planes.length + " aircraft" : "Loading…") : "Zoom in on the map", 0],
        ["Markets", statusOf("markets") || (marketsUp + " up · " + (marketRows.length - marketsUp) + " down"), 0],
        ["World news", statusOf("news") || ((feed("news").items || []).length + " headlines"), 0],
        ["Cameras", statusOf("cameras") || ((feed("cameras").items || []).length + " in London"), 0]
    ]
    function toneColour(t) { return t === 2 ? Theme.critical : t === 1 ? Theme.attention : Theme.accent }

    // ---------------------------------------------------------------- HUD status strip
    Item {
        id: header
        width: parent.width; height: 50
        opacity: atlas.reveal
        component Stat: Row {
            property string k: ""
            property string v: ""
            property color vc: Theme.accent
            spacing: 6
            Text { text: parent.k; color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 1.4 : 0.3 }
            Text { text: parent.v; color: parent.vc; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 1.2 : 0.3; font.bold: true }
        }
        Row {
            id: brand
            y: 2; spacing: 12
            ApvisMark { width: 30; height: 26; glow: 1; anchors.verticalCenter: parent.verticalCenter }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text { text: Theme.label("A T L A S"); color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 19; font.bold: true; font.letterSpacing: Theme.caps ? 3 : 0.3 }
                Text { text: Theme.label("OPEN SOURCE INTELLIGENCE"); color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7)
                       font.family: Theme.monoFont; font.pixelSize: 9; font.letterSpacing: Theme.caps ? 2.4 : 0.3 }
            }
        }
        Row {
            anchors.left: brand.right; anchors.leftMargin: 30; y: 8; spacing: 22
            Stat { k: "UTC"; v: new Date(atlas.now).toISOString().slice(11, 19) + "Z"; vc: Theme.text }
            Stat { k: "STATUS"; v: atlas.liveFeeds ? "LIVE" : "CONNECTING"; vc: atlas.liveFeeds ? Theme.accent : Theme.attention }
            Stat { k: "FEEDS"; v: atlas.liveFeeds + "/" + atlas.feedKeys.length }
            Stat { k: "LAYERS"; v: String(atlas.layersActive) }
            Stat { k: "ENTITIES"; v: atlas.entities.toLocaleString(Qt.locale("en_GB"), "f", 0) }
            Stat { k: "SOLAR"; v: atlas.kp ? "Kp" + atlas.kp.kp.toFixed(0) : "—"; vc: atlas.kp && atlas.kp.kp >= 5 ? Theme.attention : Theme.accent }
            Stat { visible: atlas.redOrange > 0; k: "ALERTS"; v: String(atlas.redOrange); vc: Theme.critical }
        }
        Text {
            anchors.left: brand.right; anchors.leftMargin: 30; y: 28
            text: Theme.label("REAL-TIME WORLD WATCH  ·  EARTHQUAKES  ·  DISASTERS  ·  STORMS  ·  WILDFIRES  ·  SPACE WEATHER  ·  AVIATION  ·  MARKETS  ·  NEWS  ·  CAMERAS")
            color: Qt.rgba(Theme.muted.r, Theme.muted.g, Theme.muted.b, 0.55); font.family: Theme.monoFont; font.pixelSize: 9; font.letterSpacing: 1.8
            width: parent.width - x - 150; elide: Text.ElideRight
        }
        Row {
            anchors.right: parent.right; y: 10; spacing: 8
            Item {
                width: 10; height: 10; anchors.verticalCenter: parent.verticalCenter
                Rectangle { anchors.centerIn: parent; width: 10; height: 10; radius: 5; color: atlas.liveFeeds ? Theme.accent : Theme.attention; opacity: 0.25
                            SequentialAnimation on scale { running: atlas.visible && !atlas.still; loops: Animation.Infinite
                                NumberAnimation { from: 0.6; to: 1.8; duration: 1400; easing.type: Easing.OutCubic } } }
                Rectangle { anchors.centerIn: parent; width: 6; height: 6; radius: 3; color: atlas.liveFeeds ? Theme.accent : Theme.attention }
            }
            Text { text: Theme.lacquer ? "APVIS" : "V2 · APVIS"; color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 1.6 : 0.3; anchors.verticalCenter: parent.verticalCenter }
        }
        Rectangle {
            anchors.bottom: parent.bottom; height: 1; width: parent.width * atlas.reveal
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.6) }
                GradientStop { position: 0.5; color: Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 0.6) }
                GradientStop { position: 1; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.35) } }
        }
    }
    Row {
        id: tiles
        visible: false; height: 0
        anchors.top: header.bottom
        spacing: 8
        readonly property real tileWidth: (view.width - 8 * 5) / 6
        StatTile { compact: true; width: tiles.tileWidth; order: 0; reveal: atlas.reveal; glyph: "activity"; tint: Theme.warm
                   label: "EARTHQUAKES 24H"; value: String(atlas.quakes.length); live: atlas.quakes.length > 0
                   sub: atlas.strongest ? "max M" + atlas.strongest.mag : "" }
        StatTile { compact: true; width: tiles.tileWidth; order: 1; reveal: atlas.reveal; glyph: "mission"; tint: atlas.redOrange ? Theme.critical : Theme.accent
                   label: "SEVERE ALERTS"; value: String(atlas.redOrange); live: atlas.redOrange > 0; sub: "GDACS" }
        StatTile { compact: true; width: tiles.tileWidth; order: 2; reveal: atlas.reveal; glyph: "activity"; tint: Theme.fire
                   label: "WILDFIRES"; value: String(atlas.fires); live: atlas.fires > 0; sub: "NASA EONET" }
        StatTile { compact: true; width: tiles.tileWidth; order: 3; reveal: atlas.reveal; glyph: "restart"; tint: Theme.signal
                   label: "STORMS"; value: String(atlas.storms); live: atlas.storms > 0; sub: "active" }
        StatTile { compact: true; width: tiles.tileWidth; order: 4; reveal: atlas.reveal; glyph: "plane"; tint: Theme.accent
                   label: "AIRCRAFT"; value: atlas.flightsVisible ? String(atlas.planes.length) : "—"; live: atlas.flightsVisible && atlas.planes.length > 0
                   sub: atlas.flightsVisible ? (atlas.info.source || "") : "zoom in" }
        StatTile { compact: true; width: tiles.tileWidth; order: 5; reveal: atlas.reveal; glyph: "atlas"
                   tint: atlas.kp && atlas.kp.kp >= 5 ? Theme.attention : Theme.kpCalm
                   label: "SPACE WEATHER"; value: atlas.kp ? "Kp " + atlas.kp.kp.toFixed(1) : "—"; live: !!atlas.kp; sub: atlas.kp ? atlas.kp.level : "" }
    }
    Column {
        id: chips
        z: 5
        x: view.x + 12; y: view.y + 56
        spacing: 6
        opacity: atlas.reveal
        Repeater {
            model: [["flights", "✈", "Flights", Theme.accent], ["quakes", "◉", "Earthquakes", Theme.warm], ["events", "▲", "Natural events", Theme.fire],
                    ["alerts", "◎", "Disasters", Theme.critical], ["iss", "✦", "ISS", Theme.text], ["cameras", "▣", "Cameras", Theme.eventColours.camera],
                    ["night", "◐", "Day / night", Theme.nightLayer]]
            delegate: AbstractButton {
                id: chip
                required property var modelData
                readonly property bool on: atlas.layersOn[modelData[0]] !== false
                readonly property color tone: modelData[3]
                readonly property int count: modelData[0] === "flights" ? (atlas.flightsVisible ? atlas.planes.length : 0)
                                             : modelData[0] === "night" ? 0 : (atlas.feed(modelData[0]).items || []).length
                width: 40; height: 40
                hoverEnabled: true
                Accessible.name: modelData[2] + (on ? " layer on" : " layer off")
                ToolTip.visible: hovered; ToolTip.delay: 300
                ToolTip.text: modelData[2] + (["night", "flights"].indexOf(modelData[0]) < 0 ? "  ·  " + atlas.layerLine(modelData[0]) : "") + (on ? "" : "  (hidden)")
                onClicked: atlas.toggle(modelData[0])
                background: Rectangle {
                    radius: 10
                    color: chip.on ? Qt.rgba(chip.tone.r, chip.tone.g, chip.tone.b, chip.hovered ? 0.22 : 0.12) : Theme.tint(Theme.atlasChipOff, chip.hovered ? 0.9 : 0.7)
                    border.width: chip.activeFocus ? 1.5 : 1
                    border.color: chip.activeFocus ? Theme.text : chip.on ? Qt.rgba(chip.tone.r, chip.tone.g, chip.tone.b, 0.55) : Theme.line
                    Behavior on color { ColorAnimation { duration: 150 } }
                }
                contentItem: Text { text: chip.modelData[1]; color: chip.on ? chip.tone : Theme.muted; font.pixelSize: 16
                                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                Rectangle {
                    visible: chip.on && chip.count > 0
                    x: parent.width - width / 2 - 4; y: -5
                    width: Math.max(18, badge.implicitWidth + 8); height: 16; radius: 8
                    color: atlas.feed(chip.modelData[0]).status === "unavailable" ? Theme.attention : chip.tone
                    Text { id: badge; anchors.centerIn: parent; text: chip.count > 999 ? Math.round(chip.count / 1000) + "k" : chip.count
                           color: Theme.atlasBadgeText; font.family: Theme.monoFont; font.pixelSize: 9; font.bold: true }
                }
            }
        }
    }

    // ---------------------------------------------------------------- map
    Item {
        id: view
        anchors.top: header.bottom; anchors.topMargin: 8
        anchors.left: parent.left; anchors.bottom: ticker.top; anchors.bottomMargin: 0
        width: parent.width
        clip: true

        property real cLat: 25
        property real cLon: 5
        property real zoom: 1
        readonly property real scale: width / 360 * zoom
        Behavior on cLat { enabled: !dragArea.pressed; NumberAnimation { duration: 500; easing.type: Easing.InOutCubic } }
        Behavior on cLon { enabled: !dragArea.pressed; NumberAnimation { duration: 500; easing.type: Easing.InOutCubic } }
        Behavior on zoom { NumberAnimation { duration: 500; easing.type: Easing.InOutCubic } }
        function merc(lat) { const r = Math.max(-85, Math.min(85, lat)) * Math.PI / 180; return Math.log(Math.tan(Math.PI / 4 + r / 2)) * 180 / Math.PI }
        function unmerc(y) { return (2 * Math.atan(Math.exp(y * Math.PI / 180)) - Math.PI / 2) * 180 / Math.PI }
        function px(lon) { let d = lon - cLon; if (d > 180) d -= 360; if (d < -180) d += 360; return width / 2 + d * scale }
        function py(lat) { return height / 2 - (merc(lat) - merc(cLat)) * scale }
        function lonAt(x) { let l = cLon + (x - width / 2) / scale; if (l > 180) l -= 360; if (l < -180) l += 360; return l }
        function latAt(y) { return unmerc(merc(cLat) + (height / 2 - y) / scale) }
        function zoomAt(factor, x, y) {
            const nz = Math.max(1, Math.min(80, zoom * factor))
            const lon = cLon + (x - width / 2) / scale, lat = latAt(y), s2 = width / 360 * nz
            cLon = lon - (x - width / 2) / s2
            cLat = Math.max(-75, Math.min(78, unmerc(merc(lat) - (height / 2 - y) / s2)))
            zoom = nz
        }
        function reset() { zoom = 1; cLat = 25; cLon = 5 }
        onScaleChanged: repaintAll()
        onCLatChanged: repaintAll()
        onCLonChanged: repaintAll()
        onWidthChanged: repaintAll()
        onHeightChanged: repaintAll()
        function repaintAll() { land_.requestPaint(); overlay.requestPaint(); areaTimer.restart() }
        Timer { id: areaTimer; interval: 1200; onTriggered: if (view.zoom >= 3) atlas.areaChanged(view.cLat, view.cLon) }

        Rectangle {
            anchors.fill: parent; radius: 2
            gradient: Gradient {
                GradientStop { position: 0; color: Theme.atlasFloorTop }
                GradientStop { position: 0.55; color: Theme.atlasFloorMid }
                GradientStop { position: 1; color: Theme.atlasFloorBottom }
            }
        }
        // Operations-room backdrop: a faint grid, a vignette and corner brackets (drawn once).
        Canvas {
            anchors.fill: parent
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                const c = getContext("2d"), w = width, h = height
                c.reset()
                c.strokeStyle = Theme.css(Theme.atlasGrid, 0.045); c.lineWidth = 1
                for (let x = 0.5; x < w; x += 48) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, h); c.stroke() }
                for (let y = 0.5; y < h; y += 48) { c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke() }
                const v = c.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.max(w, h) * 0.75)
                v.addColorStop(0, Theme.css(Theme.shadeBase, 0)); v.addColorStop(1, Theme.css(Theme.shadeBase, 0.55))
                c.fillStyle = v; c.fillRect(0, 0, w, h)
                c.strokeStyle = Theme.css(Theme.atlasGrid, 0.55); c.lineWidth = 1.5
                const L = 22, m = 6
                for (const [x, y, dx, dy] of [[m, m, 1, 1], [w - m, m, -1, 1], [m, h - m, 1, -1], [w - m, h - m, -1, -1]]) {
                    c.beginPath(); c.moveTo(x, y + dy * L); c.lineTo(x, y); c.lineTo(x + dx * L, y); c.stroke()
                }
            }
        }

        AtlasGlobe {
            id: globeView
            anchors.fill: parent
            anchors.leftMargin: 56                                     // clear of the layer rail
            anchors.rightMargin: atlas.sideOpen ? side.width + 24 : 0   // centred in the free space
            Behavior on anchors.rightMargin { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
            visible: atlas.mode === "globe"
            dots: atlas.dots
            landJson: atlas.landJson
            bordersJson: shell.worldBorders
            feeds: ({ quakes: atlas.items("quakes"), alerts: atlas.items("alerts"), events: atlas.items("events"), iss: atlas.items("iss") })
            issTrail: atlas.layersOn.iss ? atlas.issTrail : []
            selected: atlas.selected
            night: atlas.layersOn.night !== false
            still: atlas.still || !atlas.visible
            onPicked: (kind, item) => atlas.selected = { kind: kind, id: item.id }
            onOpenMap: (lat, lon) => { atlas.mode = "map"; atlas.flyTo(lat, lon, 4) }
            onPointed: where => cursorReadout.where = where
        }

        Canvas {
            id: land_
            anchors.fill: parent
            visible: atlas.mode === "map"
            renderTarget: Canvas.FramebufferObject
            property int nightTick: 0
            onNightTickChanged: if (nightTick % 60 === 0) requestPaint()     // the terminator moves slowly
            function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
            onPaint: {
                const ctx = getContext("2d"), w = width, h = height
                ctx.reset(); ctx.clearRect(0, 0, w, h)
                const glowA = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7)
                glowA.addColorStop(0, rgba(Theme.glow, 0.16)); glowA.addColorStop(1, Theme.css(Theme.shadeBase, 0))
                ctx.fillStyle = glowA; ctx.fillRect(0, 0, w, h)
                const step = view.zoom < 2.5 ? 30 : view.zoom < 8 ? 10 : view.zoom < 30 ? 2 : 1
                ctx.lineWidth = 1
                for (let lat = -80; lat <= 80; lat += step) {
                    ctx.strokeStyle = rgba(Theme.accent, lat === 0 ? 0.22 : 0.07)
                    const y = view.py(lat); ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke()
                }
                for (let lon = -180; lon < 180; lon += step) {
                    ctx.strokeStyle = rgba(Theme.accent, lon === 0 ? 0.22 : 0.07)
                    const x = view.px(lon); ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
                }
                const rings = atlas.land.rings || []
                ctx.beginPath()
                for (const ring of rings) {
                    let prevX = null
                    for (let i = 0; i < ring.length; i += 2) {
                        const x = view.px(ring[i]), y = view.py(ring[i + 1])
                        if (i === 0 || (prevX !== null && Math.abs(x - prevX) > w * 0.5)) ctx.moveTo(x, y)
                        else ctx.lineTo(x, y)
                        prevX = x
                    }
                }
                const dotsMode = view.zoom < 3.5
                ctx.fillStyle = rgba(Theme.glow, dotsMode ? 0.10 : 0.24); ctx.fill()
                ctx.strokeStyle = rgba(Theme.accent, 0.08); ctx.lineWidth = 6; ctx.stroke()
                ctx.strokeStyle = rgba(Theme.accent, dotsMode ? 0.22 : 0.45); ctx.lineWidth = 1; ctx.stroke()
                if (dotsMode) {
                    const d = atlas.dots, r = 1.1 + view.zoom * 0.35
                    ctx.fillStyle = rgba(Theme.accent, 0.16)
                    for (let i = 0; i < d.length; i += 2) {
                        const x = view.px(d[i + 1]), y = view.py(d[i])
                        if (x < -4 || x > w + 4 || y < -4 || y > h + 4) continue
                        ctx.beginPath(); ctx.arc(x, y, r * 2.2, 0, Math.PI * 2); ctx.fill()
                    }
                    ctx.fillStyle = rgba(Theme.accent, 0.75)
                    for (let i = 0; i < d.length; i += 2) {
                        const x = view.px(d[i + 1]), y = view.py(d[i])
                        if (x < -4 || x > w + 4 || y < -4 || y > h + 4) continue
                        ctx.fillRect(x - r / 2, y - r / 2, r, r)
                    }
                }
                if (view.zoom >= 6) {
                    ctx.beginPath()
                    for (const r2 of (atlas.map.rings || [])) {
                        ctx.moveTo(view.px(r2[0]), view.py(r2[1]))
                        for (let i = 2; i < r2.length; i += 2) ctx.lineTo(view.px(r2[i]), view.py(r2[i + 1]))
                    }
                    ctx.strokeStyle = rgba(Theme.text, 0.55); ctx.lineWidth = 1; ctx.stroke()
                }
                if (atlas.layersOn.night) {
                    const d = new Date()
                    const day = (Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - Date.UTC(d.getUTCFullYear(), 0, 0)) / 864e5
                    const decl = -23.44 * Math.cos(2 * Math.PI / 365 * (day + 10)) * Math.PI / 180
                    const sunLon = -(d.getUTCHours() + d.getUTCMinutes() / 60 - 12) * 15
                    const darkPole = decl > 0 ? -85 : 85
                    const X = lon => w / 2 + (lon - view.cLon) * view.scale
                    for (const shift of [-360, 0, 360]) {             // cover the wrap-around
                        ctx.beginPath()
                        ctx.moveTo(X(-180 + shift), view.py(darkPole))
                        for (let lon = -180; lon <= 180; lon += 2) {
                            const lat = Math.atan(-Math.cos((lon - sunLon) * Math.PI / 180) / Math.tan(decl)) * 180 / Math.PI
                            ctx.lineTo(X(lon + shift), view.py(lat))
                        }
                        ctx.lineTo(X(180 + shift), view.py(darkPole))
                        ctx.closePath()
                        ctx.fillStyle = Theme.css(Theme.nightSide, 0.66); ctx.fill()
                        // The day side is lifted a little, so night reads against it.
                        ctx.beginPath()
                        ctx.moveTo(X(-180 + shift), view.py(-darkPole))
                        for (let lon = -180; lon <= 180; lon += 2) {
                            const lat = Math.atan(-Math.cos((lon - sunLon) * Math.PI / 180) / Math.tan(decl)) * 180 / Math.PI
                            ctx.lineTo(X(lon + shift), view.py(lat))
                        }
                        ctx.lineTo(X(180 + shift), view.py(-darkPole))
                        ctx.closePath()
                        ctx.fillStyle = rgba(Theme.accent, 0.045); ctx.fill()
                        // Twilight: a warm band along the terminator.
                        ctx.beginPath()
                        for (let lon = -180; lon <= 180; lon += 2) {
                            const lat = Math.atan(-Math.cos((lon - sunLon) * Math.PI / 180) / Math.tan(decl)) * 180 / Math.PI
                            if (Math.abs(lat) > 84) { ctx.moveTo(X(lon + shift), view.py(lat)); continue }
                            ctx.lineTo(X(lon + shift), view.py(lat))
                        }
                        ctx.strokeStyle = Theme.css(Theme.warm, 0.07); ctx.lineWidth = 14; ctx.stroke()
                        ctx.strokeStyle = Theme.css(Theme.warm, 0.45); ctx.lineWidth = 1.2; ctx.stroke()
                    }
                    // The sunlit side glows around the point where the sun is overhead now.
                    const sunLat = decl * 180 / Math.PI
                    for (const shift of [-360, 0, 360]) {
                        const sx = X(sunLon + shift), sy = view.py(sunLat), R = 95 * view.scale
                        if (sx < -R || sx > w + R) continue
                        const sg = ctx.createRadialGradient(sx, sy, 0, sx, sy, R)
                        sg.addColorStop(0, rgba(Theme.accent, 0.13)); sg.addColorStop(0.5, rgba(Theme.accent, 0.05)); sg.addColorStop(1, rgba(Theme.accent, 0))
                        ctx.fillStyle = sg; ctx.fillRect(sx - R, sy - R, 2 * R, 2 * R)
                        if (sx < -10 || sx > w + 10) continue
                        const sun = ctx.createRadialGradient(sx, sy, 0, sx, sy, 16)
                        sun.addColorStop(0, Theme.css(Theme.sunlight, 0.9)); sun.addColorStop(0.35, Theme.css(Theme.warm, 0.35)); sun.addColorStop(1, Theme.css(Theme.warm, 0))
                        ctx.fillStyle = sun; ctx.fillRect(sx - 16, sy - 16, 32, 32)
                        ctx.strokeStyle = Theme.css(Theme.sunlight, 0.8); ctx.lineWidth = 1
                        for (let k = 0; k < 8; ++k) { const a = k * Math.PI / 4
                            ctx.beginPath(); ctx.moveTo(sx + Math.cos(a) * 7, sy + Math.sin(a) * 7); ctx.lineTo(sx + Math.cos(a) * 11, sy + Math.sin(a) * 11); ctx.stroke() }
                        ctx.fillStyle = Theme.css(Theme.sunlight, 0.85); ctx.font = "9px monospace"; ctx.fillText("SUN OVERHEAD", sx + 14, sy + 3)
                    }
                }
                // Graticule labels.
                if (step >= 10) {
                    ctx.font = "9px monospace"; ctx.fillStyle = rgba(Theme.accent, 0.5)
                    for (let lat = -60; lat <= 60; lat += step) {
                        const y = view.py(lat)
                        if (y < 40 || y > h - 40) continue
                        ctx.fillText(lat === 0 ? "EQ" : Math.abs(lat) + "°" + (lat > 0 ? "N" : "S"), 6, y - 4)
                    }
                    for (let lon = -180 + step; lon < 180; lon += step) {
                        const x = view.px(lon)
                        if (x < 340 || x > w - 80) continue
                        ctx.fillText(lon === 0 ? "0°" : Math.abs(lon) + "°" + (lon > 0 ? "E" : "W"), x + 4, 24)
                    }
                }
                if (view.zoom >= 5) {
                    ctx.font = "10px monospace"
                    for (const ap of (atlas.map.airports || [])) {
                        const x = view.px(ap[3]), y = view.py(ap[2])
                        ctx.strokeStyle = rgba(Theme.text, 0.75); ctx.lineWidth = 1.2
                        ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.stroke()
                        ctx.fillStyle = rgba(Theme.text, 0.7); ctx.fillText(ap[0], x + 6, y - 5)
                    }
                }
            }
        }

        // A slow scan line crossing the map (decoration; still with Reduce motion).
        Rectangle {
            id: sweep
            width: parent.width; height: 70
            visible: !atlas.still && atlas.mode === "map"
            gradient: Gradient {
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 0.97; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.07) }
                GradientStop { position: 1; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.35) }
            }
            SequentialAnimation on y {
                running: atlas.visible && !atlas.still; loops: Animation.Infinite
                NumberAnimation { from: -70; to: view.height; duration: 7000; easing.type: Easing.InOutSine }
                PauseAnimation { duration: 2500 }
            }
        }

        Canvas {
            id: overlay
            anchors.fill: parent
            visible: atlas.mode === "map"
            renderStrategy: Canvas.Cooperative
            readonly property var shape: [0,-1, .12,-.55, .95,.05, .95,.2, .12,.02, .1,.6, .38,.82, .38,.95, 0,.86,
                                          -.38,.95, -.38,.82, -.1,.6, -.12,.02, -.95,.2, -.95,.05, -.12,-.55]
            function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
            onPaint: {
                const ctx = getContext("2d"), w = width, h = height, g = atlas.glide
                ctx.reset(); ctx.clearRect(0, 0, w, h)
                const onScreen = (x, y) => x > -30 && y > -30 && x < w + 30 && y < h + 30
                const sel = atlas.selected
                const glow = (x, y, r, c, a) => { const gr = ctx.createRadialGradient(x, y, 0, x, y, r)
                    gr.addColorStop(0, rgba(c, a)); gr.addColorStop(1, rgba(c, 0)); ctx.fillStyle = gr; ctx.fillRect(x - r, y - r, 2 * r, 2 * r) }
                const ring = (x, y, r) => { ctx.strokeStyle = rgba(Theme.text, 1); ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.stroke()
                    ctx.strokeStyle = rgba(Theme.accent, 0.6); ctx.beginPath(); ctx.arc(x, y, r + 5, -0.5, 0.5); ctx.stroke(); ctx.beginPath(); ctx.arc(x, y, r + 5, Math.PI - 0.5, Math.PI + 0.5); ctx.stroke() }
                if (view.zoom >= 8)
                    for (const i of atlas.items("cameras")) {
                        const x = view.px(i.lon), y = view.py(i.lat)
                        if (!onScreen(x, y)) continue
                        const c = Qt.color(atlas.kindColour.camera)
                        ctx.strokeStyle = rgba(c, 0.85); ctx.lineWidth = 1; ctx.strokeRect(x - 3, y - 2.5, 6, 5)
                        ctx.fillStyle = rgba(c, 0.85); ctx.fillRect(x + 3, y - 1.2, 2, 2.4)
                        if (sel && sel.kind === "cameras" && sel.id === i.id) ring(x, y, 10)
                    }
                for (const i of atlas.items("events")) {
                    const x = view.px(i.lon), y = view.py(i.lat)
                    if (!onScreen(x, y)) continue
                    const c = Qt.color(atlas.kindColour[i.kind] || Theme.muted)
                    glow(x, y, 9, c, 0.35)
                    ctx.fillStyle = rgba(c, 0.95); ctx.strokeStyle = rgba(c, 0.95); ctx.lineWidth = 1.2
                    if (i.kind === "volcano") { ctx.beginPath(); ctx.moveTo(x, y - 5); ctx.lineTo(x + 5, y + 4); ctx.lineTo(x - 5, y + 4); ctx.closePath(); ctx.fill() }
                    else if (i.kind === "storm") {
                        ctx.beginPath(); ctx.arc(x, y, 5, 0.3, Math.PI * 1.6); ctx.stroke(); ctx.beginPath(); ctx.arc(x, y, 1.6, 0, Math.PI * 2); ctx.fill()
                        const t = i.track || []
                        if (t.length > 2) { ctx.strokeStyle = rgba(c, 0.45); ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(view.px(t[1]), view.py(t[0]))
                            for (let k = 2; k < t.length; k += 2) ctx.lineTo(view.px(t[k + 1]), view.py(t[k])); ctx.stroke(); ctx.setLineDash([]) }
                    }
                    else if (i.kind === "ice") { ctx.beginPath(); ctx.moveTo(x, y - 4); ctx.lineTo(x + 4, y); ctx.lineTo(x, y + 4); ctx.lineTo(x - 4, y); ctx.closePath(); ctx.stroke() }
                    else { ctx.beginPath(); ctx.arc(x, y, 2.4, 0, Math.PI * 2); ctx.fill() }
                    if (sel && sel.kind === "events" && sel.id === i.id) ring(x, y, 12)
                }
                for (const i of atlas.items("alerts")) {
                    const x = view.px(i.lon), y = view.py(i.lat)
                    if (!onScreen(x, y)) continue
                    const c = Qt.color(atlas.alertColour(i.alert)), r = i.alert === "Red" ? 9 : i.alert === "Orange" ? 7 : 4
                    if (i.alert !== "Green") glow(x, y, r * 3, c, 0.35)
                    ctx.strokeStyle = rgba(c, i.alert === "Green" ? 0.4 : 0.95); ctx.lineWidth = i.alert === "Red" ? 2 : 1.3
                    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.stroke()
                    if (sel && sel.kind === "alerts" && sel.id === i.id) ring(x, y, r + 7)
                }
                for (const i of atlas.items("quakes")) {
                    const x = view.px(i.lon), y = view.py(i.lat)
                    if (!onScreen(x, y)) continue
                    const r = 1.8 + Math.pow(Math.max(0, i.mag - 2), 1.4) * 1.7, c = Qt.color(i.mag >= 6 ? Theme.critical : Theme.warm)
                    glow(x, y, r * 3, c, 0.35)
                    ctx.fillStyle = rgba(c, 0.5); ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill()
                    ctx.strokeStyle = rgba(c, 0.95); ctx.lineWidth = 1; ctx.stroke()
                    if (sel && sel.kind === "quakes" && sel.id === i.id) ring(x, y, r + 7)
                }
                if (atlas.layersOn.iss) {
                    const t = atlas.issTrail
                    ctx.lineWidth = 1.4
                    for (let k = 1; k < t.length; ++k) {
                        const x0 = view.px(t[k - 1][1]), y0 = view.py(t[k - 1][0]), x1 = view.px(t[k][1]), y1 = view.py(t[k][0])
                        if (Math.abs(x1 - x0) > w * 0.5) continue
                        ctx.strokeStyle = rgba(Theme.text, 0.5 * k / t.length); ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke()
                    }
                    const iss = atlas.items("iss")[0]
                    if (iss) {
                        const x = view.px(iss.lon), y = view.py(iss.lat)
                        glow(x, y, 22, Qt.color(Theme.text), 0.35)
                        ctx.fillStyle = rgba(Theme.text, 1); ctx.strokeStyle = rgba(Theme.text, 1); ctx.lineWidth = 1.5
                        ctx.fillRect(x - 2.5, y - 2.5, 5, 5)
                        ctx.beginPath(); ctx.moveTo(x - 10, y); ctx.lineTo(x - 4, y); ctx.moveTo(x + 4, y); ctx.lineTo(x + 10, y); ctx.stroke()
                        ctx.fillRect(x - 12, y - 3, 4, 6); ctx.fillRect(x + 8, y - 3, 4, 6)
                        ctx.font = "bold 10px monospace"; ctx.fillText("ISS", x + 15, y + 4)
                        if (sel && sel.kind === "iss") ring(x, y, 16)
                    }
                }
                if (atlas.flightsVisible) {
                    ctx.lineCap = "round"
                    const nowMs = Date.now()
                    for (const p of atlas.shownPlanes) {
                        const t = p[14] || [], chosen = atlas.selectedPlane && atlas.selectedPlane[0] === p[0]
                        const col = Qt.color(atlas.colourOf(p))
                        if (t.length >= 2 && !p[7]) {
                            const n = t.length / 2
                            let x0 = view.px(t[1]), y0 = view.py(t[0])
                            for (let k = 1; k <= n; ++k) {
                                const end = k < n ? null : atlas.drawnPos(p, nowMs)
                                const x1 = k < n ? view.px(t[2 * k + 1]) : view.px(end[1]), y1 = k < n ? view.py(t[2 * k]) : view.py(end[0])
                                ctx.strokeStyle = rgba(col, (chosen ? 0.9 : 0.4) * k / n); ctx.lineWidth = chosen ? 2 : 1
                                ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke(); x0 = x1; y0 = y1
                            }
                        }
                        const pos = atlas.drawnPos(p, nowMs), lat = pos[0], lon = pos[1]
                        const x = view.px(lon), y = view.py(lat)
                        if (!onScreen(x, y)) continue
                        if (p[7]) { ctx.fillStyle = rgba(col, 0.6); ctx.beginPath(); ctx.arc(x, y, 1.8, 0, Math.PI * 2); ctx.fill(); continue }
                        const s = (chosen ? 9 : 6) * Math.min(1.6, 0.8 + view.zoom * 0.03)
                        ctx.save(); ctx.translate(x, y); ctx.rotate((p[9] === null ? 0 : p[9]) * Math.PI / 180)
                        ctx.beginPath(); ctx.moveTo(shape[0] * s, shape[1] * s)
                        for (let k = 2; k < shape.length; k += 2) ctx.lineTo(shape[k] * s, shape[k + 1] * s)
                        ctx.closePath(); ctx.fillStyle = rgba(col, chosen ? 1 : 0.92); ctx.fill(); ctx.restore()
                        if (chosen) ring(x, y, 15)
                        if (chosen || view.zoom >= 10) { ctx.font = "10px monospace"; ctx.fillStyle = rgba(chosen ? Theme.text : col, 0.85); ctx.fillText(atlas.nameOf(p), x + 10, y - 6) }
                    }
                }
            }
        }

        // Pulses for what just happened (quakes under 3 h, red alerts, the ISS).
        Canvas {
            id: pulses
            anchors.fill: parent
            visible: atlas.mode === "map"
            property real phase: 0
            NumberAnimation on phase { from: 0; to: 1; duration: 2400; loops: Animation.Infinite; running: atlas.visible && atlas.mode === "map" && !((shell.render || {}).reducedMotion) }
            onPhaseChanged: requestPaint()
            function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
            onPaint: {
                const ctx = getContext("2d"); ctx.reset(); ctx.clearRect(0, 0, width, height)
                const ping = (x, y, c, base) => { for (const off of [0, 0.5]) { const t = (phase + off) % 1
                    ctx.strokeStyle = rgba(c, 0.7 * (1 - t)); ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, base + t * 22, 0, Math.PI * 2); ctx.stroke() } }
                for (const i of atlas.items("quakes")) if (atlas.now - i.time_ms < 3 * 3600e3) ping(view.px(i.lon), view.py(i.lat), Qt.color(Theme.warm), 3)
                for (const i of atlas.items("alerts")) if (i.alert === "Red") ping(view.px(i.lon), view.py(i.lat), Qt.color(Theme.critical), 8)
                const iss = atlas.items("iss")[0]
                if (iss) ping(view.px(iss.lon), view.py(iss.lat), Qt.color(Theme.text), 4)
            }
        }

        // HUD frame: corner brackets and edge.
        Canvas {
            anchors.fill: parent
            onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
            Component.onCompleted: requestPaint()
            onPaint: {
                const c = getContext("2d"), w = width, h = height, L = 22
                c.reset(); c.clearRect(0, 0, w, h)
                const vg = c.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.38, w / 2, h / 2, Math.max(w, h) * 0.72)
                vg.addColorStop(0, Theme.css(Theme.shadeBase, 0)); vg.addColorStop(1, Theme.css(Theme.shadeBase, 0.5))
                c.fillStyle = vg; c.fillRect(0, 0, w, h)
                c.fillStyle = Theme.css(Theme.shadeBase, 0.16)
                for (let y = 0; y < h; y += 3) c.fillRect(0, y, w, 1)
                // Rulers along the edges.
                const tick = "rgba(" + Math.round(Theme.accent.r * 255) + "," + Math.round(Theme.accent.g * 255) + "," + Math.round(Theme.accent.b * 255) + ","
                c.lineWidth = 1
                for (let x = 40; x < w - 40; x += 20) {
                    const major = x % 100 === 0
                    c.strokeStyle = tick + (major ? "0.5)" : "0.22)")
                    c.beginPath(); c.moveTo(x + 0.5, 0); c.lineTo(x + 0.5, major ? 7 : 4); c.moveTo(x + 0.5, h); c.lineTo(x + 0.5, h - (major ? 7 : 4)); c.stroke()
                }
                for (let y = 40; y < h - 40; y += 20) {
                    const major = y % 100 === 0
                    c.strokeStyle = tick + (major ? "0.5)" : "0.22)")
                    c.beginPath(); c.moveTo(0, y + 0.5); c.lineTo(major ? 7 : 4, y + 0.5); c.moveTo(w, y + 0.5); c.lineTo(w - (major ? 7 : 4), y + 0.5); c.stroke()
                }
                c.strokeStyle = "rgba(" + Math.round(Theme.accent.r * 255) + "," + Math.round(Theme.accent.g * 255) + "," + Math.round(Theme.accent.b * 255) + ",0.9)"
                c.lineWidth = 2
                for (const q of [[1, 1, 1, 1], [w - 1, 1, -1, 1], [1, h - 1, 1, -1], [w - 1, h - 1, -1, -1]]) {
                    c.beginPath(); c.moveTo(q[0], q[1] + q[3] * L); c.lineTo(q[0], q[1]); c.lineTo(q[0] + q[2] * L, q[1]); c.stroke()
                }
                c.strokeStyle = "rgba(" + Math.round(Theme.accent.r * 255) + "," + Math.round(Theme.accent.g * 255) + "," + Math.round(Theme.accent.b * 255) + ",0.22)"
                c.lineWidth = 1; c.strokeRect(0.5, 0.5, w - 1, h - 1)
            }
        }
        Text {
            x: 70; y: 14
            text: Qt.formatDateTime(new Date(atlas.now), "HH:mm:ss") + " LOCAL"
            color: Theme.accent; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: 1
        }
        Text {
            id: cursorReadout
            x: 70; anchors.bottom: parent.bottom; anchors.bottomMargin: 58
            property string where: ""
            text: (where ? where + "   " : "") + (atlas.mode === "globe" ? "GLOBE   ·   drag to turn   ·   double-click a place to open the map there" :
                  "ZOOM ×" + view.zoom.toFixed(1) +
                  (atlas.layersOn.flights && view.zoom < 3 ? "   ·   zoom into a region (or press UK) to load live aircraft" : ""))
            color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10
        }

        MouseArea {
            id: dragArea
            anchors.fill: parent
            enabled: atlas.mode === "map"
            visible: enabled
            hoverEnabled: true
            property real lastX: 0
            property real lastY: 0
            property bool moved: false
            cursorShape: pressed && moved ? Qt.ClosedHandCursor : Qt.CrossCursor
            onPressed: mouse => { lastX = mouse.x; lastY = mouse.y; moved = false }
            onPositionChanged: mouse => {
                const la = view.latAt(mouse.y), lo = view.lonAt(mouse.x)
                cursorReadout.where = Math.abs(la).toFixed(2) + "°" + (la >= 0 ? "N" : "S") + "  " + Math.abs(lo).toFixed(2) + "°" + (lo >= 0 ? "E" : "W")
                if (!pressed) return
                const dx = mouse.x - lastX, dy = mouse.y - lastY
                if (Math.abs(dx) + Math.abs(dy) > 2) { moved = true; atlas.followHex = "" }
                if (!moved) return
                let lon = view.cLon - dx / view.scale
                if (lon > 180) lon -= 360
                if (lon < -180) lon += 360
                view.cLon = lon
                view.cLat = Math.max(-75, Math.min(78, view.unmerc(view.merc(view.cLat) + dy / view.scale)))
                lastX = mouse.x; lastY = mouse.y
            }
            onExited: cursorReadout.where = ""
            onReleased: mouse => {
                if (moved) return
                let best = null, bestD = 16 * 16
                const consider = (x, y, pick) => { const d = (x - mouse.x) * (x - mouse.x) + (y - mouse.y) * (y - mouse.y); if (d < bestD) { bestD = d; best = pick } }
                for (const p of atlas.shownPlanes) consider(view.px(p[5]), view.py(p[4]), { kind: "plane", hex: p[0] })
                const keys = ["alerts", "quakes", "events", "iss"].concat(view.zoom >= 8 ? ["cameras"] : [])
                for (const k of keys)
                    for (const i of atlas.items(k)) consider(view.px(i.lon), view.py(i.lat), { kind: k, id: i.id })
                atlas.selected = best
            }
            onDoubleClicked: view.reset()
            onWheel: wheel => view.zoomAt(wheel.angleDelta.y > 0 ? 1.4 : 1 / 1.4, wheel.x, wheel.y)
        }
        focus: true
        activeFocusOnTab: true
        Accessible.name: "World map. Plus and minus zoom, arrow keys move, zero shows the whole world."
        Keys.onPressed: event => {
            const step = 80 / view.scale
            if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal) view.zoomAt(1.4, view.width / 2, view.height / 2)
            else if (event.key === Qt.Key_Minus) view.zoomAt(1 / 1.4, view.width / 2, view.height / 2)
            else if (event.key === Qt.Key_0) view.reset()
            else if (event.key === Qt.Key_Left) view.cLon -= step
            else if (event.key === Qt.Key_Right) view.cLon += step
            else if (event.key === Qt.Key_Up) view.cLat = Math.min(78, view.cLat + step)
            else if (event.key === Qt.Key_Down) view.cLat = Math.max(-75, view.cLat - step)
            else return
            event.accepted = true
        }
        Column {
            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 6
            anchors.rightMargin: atlas.sideOpen ? side.width + 24 : 12
            Behavior on anchors.rightMargin { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
            HudButton { width: 40; implicitHeight: 32; caption: atlas.sideOpen ? "⟫" : "⟪"; tone: atlas.sideOpen ? "selected" : "normal"
                        Accessible.name: atlas.sideOpen ? "Hide the intel panel" : "Show the intel panel"
                        onClicked: atlas.sideOpen = !atlas.sideOpen
                        ToolTip.visible: hovered; ToolTip.text: atlas.sideOpen ? "Hide intel panel" : "Show intel panel" }
            HudButton { width: 40; implicitHeight: 32; caption: "+"; Accessible.name: "Zoom in"
                        onClicked: atlas.mode === "globe" ? globeView.zoom = Math.min(2.4, globeView.zoom * 1.2) : view.zoomAt(1.4, view.width / 2, view.height / 2) }
            HudButton { width: 40; implicitHeight: 32; caption: "−"; Accessible.name: "Zoom out"
                        onClicked: atlas.mode === "globe" ? globeView.zoom = Math.max(0.6, globeView.zoom / 1.2) : view.zoomAt(1 / 1.4, view.width / 2, view.height / 2) }
            HudButton { width: 40; implicitHeight: 32; caption: "⌂"; Accessible.name: "Whole world"
                        onClicked: { if (atlas.mode === "globe") { globeView.zoom = 1; globeView.focusOn(18, globeView.lon0) } else view.reset() } }
            HudButton { width: 40; implicitHeight: 32; caption: "UK"; Accessible.name: "Go to the UK"; onClicked: { atlas.mode = "map"; atlas.flyTo(54.5, -3.5, 7) } }
            HudButton { width: 40; implicitHeight: 32; caption: "LDN"; Accessible.name: "Go to London (traffic cameras)"; onClicked: { atlas.mode = "map"; atlas.flyTo(51.507, -0.13, 18) } }
        }
        Segmented {
            x: 70; anchors.bottom: parent.bottom; anchors.bottomMargin: 20
            options: ["globe", "map"]
            value: atlas.mode
            label: v => v === "globe" ? "Globe" : "Map"
            onPicked: v => atlas.mode = v
        }
    }

    // ---------------------------------------------------------------- markets ticker (delayed quotes)
    Item {
        id: ticker
        anchors.left: parent.left; anchors.bottom: attribution.top; anchors.bottomMargin: 4
        width: parent.width; height: 28
        clip: true
        readonly property var rows: atlas.feed("markets").items || []
        // Latest strong quakes and severe alerts ride the tape too.
        readonly property var events: atlas.quakes.filter(q => q.mag >= 4.5).slice(0, 6).map(q => ({ title: "M" + q.mag.toFixed(1) + " " + (q.place || q.title || ""), ev: true }))
                                       .concat((atlas.feed("alerts").items || []).filter(a => a.alert && a.alert !== "Green").slice(0, 4).map(a => ({ title: a.alert.toUpperCase() + " · " + a.title, ev: true })))
        Rectangle { anchors.fill: parent
                    gradient: Gradient { GradientStop { position: 0; color: Theme.marketTop } GradientStop { position: 1; color: Theme.marketBase } }
                    border.color: Theme.marketLine; border.width: 1 }
        Row {
            id: tape
            x: 0; y: 6; spacing: 30
            Repeater {
                model: ticker.rows.concat(ticker.events, ticker.rows, ticker.events)   // twice, for a seamless loop
                delegate: Row {
                    required property var modelData
                    spacing: 7
                    Rectangle { visible: !!modelData.ev; width: 6; height: 6; radius: 3; color: Theme.warm; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: modelData.ev ? modelData.title : Theme.upper(modelData.title); color: modelData.ev ? Theme.warm : Theme.muted
                           font.family: Theme.monoFont; font.pixelSize: 11 }
                    Text { visible: !modelData.ev; text: modelData.ev ? "" : atlas.fmtPrice(modelData); color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 11 }
                    Text { visible: !modelData.ev; text: modelData.ev || modelData.change_pct === null || modelData.change_pct === undefined ? "" : (modelData.change_pct >= 0 ? "▲ " : "▼ ") + Math.abs(modelData.change_pct).toFixed(2) + "%"
                           color: modelData.change_pct >= 0 ? Theme.gain : Theme.loss; font.family: Theme.monoFont; font.pixelSize: 11 }
                }
            }
            NumberAnimation on x {
                running: atlas.visible && ticker.rows.length > 0 && !((shell.render || {}).reducedMotion)
                from: tapeLabel.width + 10; to: tapeLabel.width + 10 - tape.width / 2 - 15; duration: Math.max(20000, tape.width * 25); loops: Animation.Infinite
            }
        }
        Text { visible: ticker.rows.length === 0; anchors.centerIn: parent; text: "Markets: " + atlas.layerLine("markets")
               color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10 }
        // Fade the tape at the ends, and a label block on the left.
        Rectangle { anchors.right: online.left; width: 50; height: parent.height
                    gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: Theme.marketBase } } }
        Rectangle {
            id: online
            anchors.right: parent.right; width: onlineText.implicitWidth + 26; height: parent.height
            color: Theme.marketBase; border.color: Theme.marketLine; border.width: 1
            Row {
                anchors.centerIn: parent; spacing: 6
                Rectangle { width: 7; height: 7; radius: 3.5; anchors.verticalCenter: parent.verticalCenter; color: atlas.liveFeeds ? Theme.accent : Theme.attention }
                Text { id: onlineText; text: atlas.liveFeeds ? Theme.label("ONLINE") : Theme.label("OFFLINE"); color: atlas.liveFeeds ? Theme.accent : Theme.attention
                       font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 1.4 : 0.3; font.bold: true }
            }
        }
        Rectangle {
            id: tapeLabel
            width: tapeLabelText.implicitWidth + 22; height: parent.height
            color: Theme.marketBadge; border.color: Theme.marketLine; border.width: 1
            Text { id: tapeLabelText; anchors.centerIn: parent; text: Theme.label("MARKETS  ") + (atlas.marketRows.length ? atlas.marketsUp + "▲ " + (atlas.marketRows.length - atlas.marketsUp) + "▼" : "")
                   color: Theme.gain; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 1.4 : 0.3; font.bold: true }
        }
        Rectangle { x: tapeLabel.width; width: 40; height: parent.height
                    gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: Theme.marketFade } GradientStop { position: 1; color: "transparent" } } }
    }
    Text {
        id: attribution
        anchors.bottom: parent.bottom; anchors.left: parent.left
        width: parent.width; elide: Text.ElideRight
        text: "Sources: " + ["quakes", "events", "alerts", "iss", "space", "cameras", "markets", "news"].map(k => atlas.feed(k).source).filter(s => s).join(", ") +
              (atlas.info.attribution ? " · " + atlas.info.attribution : "") + " · Land: Natural Earth · Night shadow computed · Market prices delayed"
        color: Theme.muted; font.pixelSize: 9
    }

    // ---------------------------------------------------------------- side panel
    Item {
        id: side
        z: 6
        anchors.top: view.top; anchors.topMargin: 10; anchors.bottom: view.bottom; anchors.bottomMargin: 10
        x: atlas.sideOpen ? parent.width - width - 10 : parent.width + 20
        opacity: atlas.sideOpen ? 1 : 0
        visible: opacity > 0.01
        Behavior on x { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 260 } }
        width: Math.min(360, parent.width * 0.3)
        property string tab: "events"

        Item {
            id: selCard
            width: parent.width; height: selCol.height + 26
            Behavior on height { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
            clip: true
            Chamfer { anchors.fill: parent; cut: 12; fill: Theme.raised; fillOpacity: 0.85; fill2: Theme.bgBottom; fill2Opacity: 0.85; brackets: true
                      edgeGlow: !!atlas.selectedPlane || !!atlas.selectedItem
                      glowColour: atlas.selectedPlane ? atlas.colourOf(atlas.selectedPlane) : atlas.selectedItem ? atlas.colourOfItem(atlas.selectedItem) : Theme.accent
                      stroke: atlas.selectedPlane ? atlas.colourOf(atlas.selectedPlane) : atlas.selectedItem ? atlas.colourOfItem(atlas.selectedItem) : Theme.line }
            Column {
                id: selCol
                x: 14; y: 13; width: parent.width - 28; spacing: 6
                Column {
                    visible: !atlas.selectedPlane && !atlas.selectedItem
                    width: parent.width; spacing: 4
                    Item {
                        width: parent.width; height: 22
                        Text { text: Theme.label("GLOBAL OVERVIEW"); color: Theme.text; font.pixelSize: 12; font.letterSpacing: 1.8; font.weight: Font.Medium }
                        Text { anchors.right: parent.right; text: atlas.liveFeeds + " / " + atlas.feedKeys.length + " live"; color: Theme.accent; font.pixelSize: 11 }
                    }
                    Repeater {
                        model: atlas.overview
                        delegate: Item {
                            required property var modelData
                            width: parent.width; height: 24
                            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 7; height: 7; radius: 3.5; color: atlas.toneColour(modelData[2]) }
                            Text { x: 16; anchors.verticalCenter: parent.verticalCenter; text: modelData[0]; color: Theme.text; font.pixelSize: 13 }
                            Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: modelData[1]
                                   color: modelData[1] === "Offline" ? Theme.attention : modelData[2] ? atlas.toneColour(modelData[2]) : Theme.accent; font.pixelSize: 12 }
                        }
                    }
                    Text { width: parent.width; wrapMode: Text.WordWrap; topPadding: 4
                           text: "Click an event on the globe or in the list. LDN opens the live London traffic cameras."
                           color: Theme.muted; font.pixelSize: 11 }
                }
                Text { visible: !!atlas.selectedItem; width: parent.width; wrapMode: Text.WordWrap
                       text: atlas.selectedItem ? atlas.selectedItem.title : ""; color: Theme.text; font.pixelSize: 16; font.weight: Font.DemiBold }
                Text { visible: !!atlas.selectedItem; width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 12
                       text: !atlas.selectedItem ? "" : [atlas.selectedItem.detail, atlas.selectedItem.alert ? atlas.selectedItem.alert + " alert" : "",
                             atlas.selectedItem.depth_km ? atlas.selectedItem.depth_km.toFixed(0) + " km deep" : "",
                             atlas.selectedItem.tsunami ? "tsunami flag" : "", atlas.whenOf(atlas.selectedItem)].filter(x => x).join("  ·  ") }
                Image {
                    id: camImage
                    visible: !!atlas.selectedItem && !!atlas.selectedItem.image
                    width: parent.width; height: visible ? width * 0.56 : 0
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true; cache: false
                    source: atlas.selectedItem && atlas.selectedItem.image ? atlas.selectedItem.image + "?t=" + Math.floor(atlas.now / 60000) : ""
                    Rectangle { anchors.fill: parent; color: "transparent"; border.color: Theme.line }
                    Text { anchors.centerIn: parent; visible: camImage.status !== Image.Ready
                           text: camImage.status === Image.Error ? "Camera image unavailable" : "Loading camera…"; color: Theme.muted; font.pixelSize: 11 }
                }
                Text { visible: !!atlas.selectedItem && atlas.selectedItem.lat !== undefined; color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10
                       text: atlas.selectedItem && atlas.selectedItem.lat !== undefined ? atlas.selectedItem.lat.toFixed(3) + ", " + atlas.selectedItem.lon.toFixed(3) + "  ·  " +
                                                  (atlas.selectedItem.source || atlas.feed(atlas.selected.kind).source) : "" }
                Text { visible: !!atlas.selectedItem && !!atlas.selectedItem.url; width: parent.width; elide: Text.ElideMiddle
                       text: atlas.selectedItem ? atlas.selectedItem.url || "" : ""; color: Theme.accent; font.pixelSize: 10 }
                Row {
                    visible: !!atlas.selectedPlane; spacing: 8
                    Glyph { width: 18; height: 18; kind: "plane"; stroke: atlas.selectedPlane ? atlas.colourOf(atlas.selectedPlane) : Theme.accent }
                    Text { text: atlas.selectedPlane ? atlas.nameOf(atlas.selectedPlane) : ""; color: Theme.text; font.pixelSize: 19; font.weight: Font.DemiBold }
                }
                Text {
                    visible: !!atlas.selectedPlane; width: parent.width; wrapMode: Text.WordWrap; color: Theme.text; font.pixelSize: 12; lineHeight: 1.3
                    text: !atlas.selectedPlane ? "" : [atlas.selectedPlane[13] || atlas.selectedPlane[3], atlas.selectedPlane[2]].filter(x => x).join(" · ") +
                          "\n" + atlas.heightOf(atlas.selectedPlane) + " " + atlas.trend(atlas.selectedPlane) +
                          (atlas.selectedPlane[8] === null ? "" : "  ·  " + atlas.selectedPlane[8] + " kt") +
                          (atlas.selectedPlane[9] === null ? "" : "  ·  " + ("00" + atlas.selectedPlane[9]).slice(-3) + "°") +
                          "\nPosition " + atlas.selectedPlane[10] + " s old  ·  " + (atlas.info.source || "") +
                          "\nBetween updates the icon moves by its reported speed and heading."
                }
                HudButton { visible: !!atlas.selectedPlane; width: 180; glyph: "mission"; tone: "primary"
                            caption: atlas.selectedPlane && atlas.followHex === atlas.selectedPlane[0] ? "Following" : "Focus this flight"
                            onClicked: atlas.focusPlane(atlas.selectedPlane) }
                // The photo (Wikimedia Commons, credited), once the flight is focused.
                Item {
                    visible: !!atlas.selectedPlane && !!atlas.photo.state
                    width: parent.width; height: visible ? photoCol.height : 0
                    Column {
                        id: photoCol
                        width: parent.width; spacing: 4
                        Item {
                            width: parent.width; height: atlas.photo.state === "ready" ? Math.round(width * 0.6) : 30
                            Rectangle { anchors.fill: parent; color: Theme.sheen(0.04); border.color: Theme.line; radius: 3 }
                            Image {
                                id: planeImage
                                anchors.fill: parent; anchors.margins: 1
                                visible: atlas.photo.state === "ready"
                                source: atlas.photo.state === "ready" ? atlas.photo.url : ""
                                fillMode: Image.PreserveAspectCrop; asynchronous: true; smooth: true; mipmap: true
                                sourceSize.width: 640
                            }
                            Text { anchors.centerIn: parent; visible: atlas.photo.state !== "ready" || planeImage.status !== Image.Ready
                                   text: atlas.photo.state === "loading" || planeImage.status === Image.Loading ? "Finding a photo…" : "No photo of this aircraft on Wikimedia Commons"
                                   color: Theme.muted; font.pixelSize: 11 }
                            Rectangle {
                                visible: atlas.photo.state === "ready"
                                anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 6
                                width: matchText.implicitWidth + 12; height: 18; radius: 3; color: Theme.shade(0.6)
                                Text { id: matchText; anchors.centerIn: parent; color: Theme.accent; font.pixelSize: 9; font.letterSpacing: 1.2
                                       text: Theme.label(atlas.photo.match === "this aircraft" ? "THIS AIRCRAFT" : "SAME TYPE") }
                            }
                        }
                        Text { visible: atlas.photo.state === "ready"; width: parent.width; elide: Text.ElideRight; maximumLineCount: 1
                               text: atlas.photo.caption || ""; color: Theme.text; font.pixelSize: 11 }
                        Text { visible: atlas.photo.state === "ready"; width: parent.width; elide: Text.ElideRight
                               text: "Wikimedia Commons" + (atlas.photo.credit ? "  ·  " + atlas.photo.credit : ""); color: Theme.muted; font.pixelSize: 10 }
                    }
                }
            }
        }

        Segmented {
            id: tabs
            anchors.top: selCard.bottom; anchors.topMargin: 10
            width: parent.width; fill: true
            options: ["events", "news", "markets", "flights"]
            value: side.tab
            label: v => v === "events" ? "Events" : v === "news" ? "News" : v === "markets" ? "Markets" : "Flights"
            onPicked: v => side.tab = v
        }
        Chamfer {
            anchors.top: tabs.bottom; anchors.topMargin: 6; anchors.bottom: parent.bottom
            width: parent.width; cut: 12
            fill: side.tab === "markets" ? Theme.marketPanel : Theme.raised; fillOpacity: 0.7
            fill2: side.tab === "markets" ? Theme.marketBase : Theme.bgBottom; fill2Opacity: 0.8
            stroke: side.tab === "markets" ? Theme.marketLine : Theme.line
            edgeGlow: true; glowColour: side.tab === "markets" ? Theme.gain : Theme.accent
        }

        ListView {
            visible: side.tab === "events"
            anchors.top: tabs.bottom; anchors.topMargin: 14; anchors.bottom: parent.bottom; anchors.bottomMargin: 8
            x: 8; width: parent.width - 10; clip: true; spacing: 2
            model: atlas.eventFeed
            ScrollBar.vertical: HudScrollBar {}
            delegate: ItemDelegate {
                id: ev
                required property var modelData
                width: ListView.view.width - 10; height: 42
                focusPolicy: Qt.NoFocus
                Accessible.name: modelData.item.title + ", " + modelData.item.detail
                contentItem: Row {
                    spacing: 10
                    Rectangle { width: 3; height: 28; radius: 1.5; anchors.verticalCenter: parent.verticalCenter; color: atlas.colourOfItem(ev.modelData.item) }
                    Column {
                        width: ev.width - 30 - tag.width - 8; anchors.verticalCenter: parent.verticalCenter
                        Text { width: parent.width; elide: Text.ElideRight; text: ev.modelData.item.title; color: Theme.text; font.pixelSize: 12 }
                        Text { width: parent.width; elide: Text.ElideRight; color: Theme.muted; font.pixelSize: 10
                               text: [ev.modelData.item.detail, atlas.whenOf(ev.modelData.item), atlas.feed(ev.modelData.layer).source].filter(x => x).join(" · ") }
                    }
                    Rectangle {
                        id: tag
                        readonly property color tone: atlas.colourOfItem(ev.modelData.item)
                        anchors.verticalCenter: parent.verticalCenter
                        width: tagText.implicitWidth + 12; height: 18; radius: 3
                        color: Qt.rgba(tone.r, tone.g, tone.b, 0.12); border.width: 1; border.color: Qt.rgba(tone.r, tone.g, tone.b, 0.5)
                        Text { id: tagText; anchors.centerIn: parent; color: tag.tone; font.family: Theme.monoFont; font.pixelSize: 9; font.letterSpacing: 1
                               text: ev.modelData.item.mag !== undefined ? "M" + ev.modelData.item.mag.toFixed(1) :
                                     ev.modelData.item.alert ? ev.modelData.item.alert.toUpperCase() : (ev.modelData.item.kind || "").toUpperCase() }
                    }
                }
                background: Rectangle { radius: 3
                    color: atlas.selected && atlas.selected.id === ev.modelData.item.id ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.14) :
                           ev.hovered ? Theme.hover : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } } }
                onClicked: atlas.selectItem(ev.modelData.layer, ev.modelData.item)
            }
        }

        // World news (not placed on the map: the sources do not give a place).
        ListView {
            visible: side.tab === "news"
            anchors.top: tabs.bottom; anchors.topMargin: 14; anchors.bottom: parent.bottom; anchors.bottomMargin: 8
            x: 8; width: parent.width - 10; clip: true; spacing: 2
            model: atlas.feed("news").items || []
            ScrollBar.vertical: HudScrollBar {}
            header: Text { width: ListView.view ? ListView.view.width : 300; bottomPadding: 6; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 10
                           text: "World politics, conflict and elections · " + atlas.layerLine("news") }
            delegate: ItemDelegate {
                id: nw
                required property var modelData
                width: ListView.view.width - 10; height: newsCol.height + 12
                focusPolicy: Qt.NoFocus
                contentItem: Column {
                    id: newsCol
                    spacing: 2
                    Text { width: nw.width - 20; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                           text: nw.modelData.title; color: Theme.text; font.pixelSize: 12 }
                    Text { width: nw.width - 20; elide: Text.ElideRight; color: Theme.muted; font.pixelSize: 10
                           text: [nw.modelData.source, nw.modelData.detail, atlas.whenOf(nw.modelData)].filter(x => x).join(" · ") }
                }
                background: Rectangle { radius: 3; color: atlas.selected && atlas.selected.id === nw.modelData.id ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.14) :
                                                              nw.hovered ? Theme.hover : "transparent" }
                onClicked: atlas.selected = { kind: "news", id: modelData.id }
            }
        }

        // Markets: black-green terminal panel.
        ListView {
            visible: side.tab === "markets"
            anchors.top: tabs.bottom; anchors.topMargin: 14; anchors.bottom: parent.bottom; anchors.bottomMargin: 8
            x: 8; width: parent.width - 10; clip: true; spacing: 6
            model: atlas.feed("markets").items || []
            ScrollBar.vertical: HudScrollBar {}
            header: Item {
                width: ListView.view ? ListView.view.width - 10 : 300; height: 62
                Text { y: 2; text: Theme.label("GLOBAL MARKETS"); color: Theme.gain; font.family: Theme.monoFont; font.pixelSize: 11; font.letterSpacing: Theme.caps ? 2 : 0.3; font.bold: true }
                Text { anchors.right: parent.right; y: 2; text: atlas.marketsUp + " ▲   " + (atlas.marketRows.length - atlas.marketsUp) + " ▼"
                       color: Theme.marketText; font.family: Theme.monoFont; font.pixelSize: 11 }
                // Market mood: share of quotes that are up today.
                Rectangle {
                    y: 24; width: parent.width; height: 6; radius: 3; color: Theme.marketLossTrack
                    Rectangle { height: parent.height; radius: 3; color: Theme.gain
                                width: parent.width * (atlas.marketRows.length ? atlas.marketsUp / atlas.marketRows.length : 0.5)
                                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } } }
                }
                Text { y: 38; width: parent.width; elide: Text.ElideRight; color: Theme.marketMuted; font.pixelSize: 10
                       text: "Delayed quotes, not advice · " + atlas.layerLine("markets") }
            }
            delegate: Item {
                id: mk
                required property var modelData
                readonly property bool up: (modelData.change_pct || 0) >= 0
                readonly property color tone: up ? Theme.gain : Theme.loss
                width: ListView.view.width - 10; height: 66
                Rectangle {
                    anchors.fill: parent; radius: 4
                    gradient: Gradient { orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: mk.up ? Theme.marketUpTop : Theme.marketDownTop }
                        GradientStop { position: 0.45; color: Theme.marketMid }
                        GradientStop { position: 1; color: Theme.marketBase } }
                    border.color: Qt.rgba(mk.tone.r, mk.tone.g, mk.tone.b, 0.3); border.width: 1
                }
                Rectangle { x: 0; y: 10; width: 2; height: parent.height - 20; color: mk.tone }
                Column {
                    x: 12; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                    Text { text: Theme.upper(mk.modelData.title); color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10; font.letterSpacing: Theme.caps ? 1.2 : 0.3 }
                    Text { text: atlas.fmtPrice(mk.modelData) + (mk.modelData.currency ? "  " + mk.modelData.currency : "")
                           color: Theme.marketValue; font.family: Theme.monoFont; font.pixelSize: 17; font.weight: Font.DemiBold }
                    Text { text: mk.modelData.change_pct === null ? "" : (mk.up ? "▲ +" : "▼ ") + mk.modelData.change_pct.toFixed(2) + "%   " + atlas.whenOf(mk.modelData)
                           color: mk.tone; font.family: Theme.monoFont; font.pixelSize: 10 }
                }
                Canvas {
                    id: spark
                    anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                    width: parent.width * 0.42; height: 40
                    readonly property var s: mk.modelData.series || []
                    onSChanged: requestPaint()
                    Component.onCompleted: requestPaint()
                    onPaint: {
                        const c = getContext("2d"), w = width, h = height, s = spark.s
                        c.reset(); c.clearRect(0, 0, w, h)
                        const col = mk.tone
                        const rgb = Math.round(col.r * 255) + "," + Math.round(col.g * 255) + "," + Math.round(col.b * 255)
                        if (s.length < 2) { c.fillStyle = "rgba(" + rgb + ",0.6)"; c.font = "9px monospace"; c.fillText("24 h change", w - 70, h / 2 + 3); return }
                        const lo = Math.min(...s), hi = Math.max(...s), span = hi - lo || 1
                        const X = i => i / (s.length - 1) * w, Y = v => h - 3 - (v - lo) / span * (h - 6)
                        const grad = c.createLinearGradient(0, 0, 0, h)
                        grad.addColorStop(0, "rgba(" + rgb + ",0.35)"); grad.addColorStop(1, "rgba(" + rgb + ",0)")
                        c.beginPath(); c.moveTo(0, h)
                        for (let i = 0; i < s.length; ++i) c.lineTo(X(i), Y(s[i]))
                        c.lineTo(w, h); c.closePath(); c.fillStyle = grad; c.fill()
                        c.beginPath(); c.moveTo(X(0), Y(s[0]))
                        for (let i = 1; i < s.length; ++i) c.lineTo(X(i), Y(s[i]))
                        c.strokeStyle = "rgba(" + rgb + ",0.22)"; c.lineWidth = 5; c.stroke()
                        c.strokeStyle = "rgb(" + rgb + ")"; c.lineWidth = 1.5; c.stroke()
                        const pv = mk.modelData.previous
                        if (pv && pv >= lo && pv <= hi) { c.setLineDash([2, 3]); c.strokeStyle = Theme.css(Theme.marketPrevious, 0.45); c.lineWidth = 1
                            c.beginPath(); c.moveTo(0, Y(pv)); c.lineTo(w, Y(pv)); c.stroke(); c.setLineDash([]) }
                        const ex = X(s.length - 1), ey = Y(s[s.length - 1])
                        const halo = c.createRadialGradient(ex, ey, 0, ex, ey, 9)
                        halo.addColorStop(0, "rgba(" + rgb + ",0.6)"); halo.addColorStop(1, "rgba(" + rgb + ",0)")
                        c.fillStyle = halo; c.fillRect(ex - 9, ey - 9, 18, 18)
                        c.fillStyle = "rgb(" + rgb + ")"
                        c.beginPath(); c.arc(ex, ey, 2.5, 0, Math.PI * 2); c.fill()
                    }
                }
            }
        }

        Item {
            visible: side.tab === "flights"
            anchors.top: tabs.bottom; anchors.topMargin: 14; anchors.bottom: parent.bottom; anchors.bottomMargin: 8
            x: 10; width: parent.width - 20
            Text { id: fHead; width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 11
                   text: view.zoom < 3 ? "Zoom into a region (or press UK) to load live aircraft there." :
                         atlas.live ? atlas.planes.length + " aircraft · " + (atlas.info.source || "") +
                                      (atlas.stats.climbing !== undefined ? "   ▲ " + atlas.stats.climbing + " climbing  ▼ " + atlas.stats.descending + " descending" : "")
                                    : (atlas.info.error || "Waiting for the first update…") }
            TextField {
                id: findField
                anchors.top: fHead.bottom; anchors.topMargin: 6
                width: parent.width; height: 32
                placeholderText: "Find callsign, registration or type…"; verticalAlignment: TextInput.AlignVCenter
                color: Theme.text; placeholderTextColor: Theme.muted; selectByMouse: true; font.pixelSize: 12
                Accessible.name: "Find aircraft"
                leftPadding: 10
                background: Chamfer { cut: 8; fill: Theme.bgBottom; fillOpacity: 0.6
                                      stroke: findField.activeFocus ? Theme.accent : Theme.line; strokeWidth: findField.activeFocus ? 1.5 : 1 }
                onTextChanged: atlas.filterText = text.trim()
            }
            ListView {
                anchors.top: findField.bottom; anchors.topMargin: 6; anchors.bottom: parent.bottom
                width: parent.width; clip: true
                model: atlas.shownPlanes
                ScrollBar.vertical: HudScrollBar {}
                delegate: ItemDelegate {
                    id: row
                    required property var modelData
                    focusPolicy: Qt.NoFocus
                    width: ListView.view.width - 10; height: 26
                    Accessible.name: atlas.nameOf(modelData) + ", " + atlas.heightOf(modelData)
                    contentItem: Row {
                        spacing: 8
                        Rectangle { width: 6; height: 6; radius: 3; color: atlas.colourOf(row.modelData); anchors.verticalCenter: parent.verticalCenter }
                        Text { width: 86; text: atlas.nameOf(row.modelData); elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter
                               color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 11 }
                        Text { width: 44; text: row.modelData[3]; color: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: atlas.heightOf(row.modelData) + " " + atlas.trend(row.modelData); color: Theme.muted; font.pixelSize: 11
                               anchors.verticalCenter: parent.verticalCenter }
                    }
                    background: Rectangle { radius: 3; color: row.hovered ? Theme.hover : "transparent" }
                    onClicked: { atlas.selected = { kind: "plane", hex: modelData[0] }; atlas.flyTo(modelData[4], modelData[5], view.zoom) }
                }
            }
        }
    }
}
