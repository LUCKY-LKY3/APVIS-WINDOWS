import QtQuick
import "../theme"

// LIVE INTELLIGENCE (owner concept): a small world map with what is happening
// now, and one status per domain worked out from the real public feeds (USGS,
// GDACS, NASA EONET, NOAA SWPC, markets). Loading and offline say so.
GlassCard {
    id: card
    title: "LIVE INTELLIGENCE"
    signal go(string key)
    onOpened: go("atlas")
    readonly property var world: JSON.parse(shell.atlasWorld || "{}")
    readonly property var land: JSON.parse(shell.worldLand || "{}")
    function feed(k) { return world[k] || {} }
    function items(k) { return feed(k).items || [] }
    function st(k) { return feed(k).status || "" }
    function wait(k) { return st(k) === "unavailable" ? "Offline" : "Loading…" }       // not live yet, or down
    readonly property var quakes: items("quakes")
    readonly property var strongest: quakes.reduce((a, q) => !a || q.mag > a.mag ? q : a, null)
    readonly property int severe: items("alerts").filter(i => i.alert === "Red" || i.alert === "Orange").length
    readonly property int red: items("alerts").filter(i => i.alert === "Red").length
    readonly property int storms: items("events").filter(i => i.kind === "storm").length + items("alerts").filter(i => i.kind === "cyclone").length
    readonly property int fires: items("events").filter(i => i.kind === "fire").length
    readonly property var kp: items("space")[0]
    readonly property var markets: items("markets")
    readonly property int up: markets.filter(m => (m.change_pct || 0) >= 0).length
    onWorldChanged: map.requestPaint()
    onLandChanged: map.requestPaint()

    // [label, value, tone] per domain; tone: 0 calm, 1 notable, 2 severe
    readonly property var rows: [
        ["Earthquakes", st("quakes") !== "live" ? wait("quakes") :
                        strongest && strongest.mag >= 6 ? "M" + strongest.mag.toFixed(1) + " today" : quakes.length + " · normal",
                        strongest && strongest.mag >= 6 ? 1 : 0],
        ["Disasters", st("alerts") !== "live" ? wait("alerts") : severe ? severe + " severe" : "Normal", red ? 2 : severe ? 1 : 0],
        ["Weather", st("events") !== "live" ? wait("events") : storms + " storms · " + fires + " fires", storms > 5 ? 1 : 0],
        ["Space weather", !kp ? wait("space") : "Kp " + kp.kp.toFixed(1) + " · " + kp.level, kp && kp.kp >= 5 ? 1 : 0],
        ["Markets", !markets.length ? wait("markets") : up + " up · " + (markets.length - up) + " down", 0]
    ]
    function toneColour(t) { return t === 2 ? Theme.critical : t === 1 ? Theme.attention : Theme.accent }

    Item {
        width: parent.width; height: 158
        Canvas {
            id: map
            width: parent.width * (parent.width >= 400 ? 0.46 : 0.34); height: parent.height
            onWidthChanged: requestPaint()
            Component.onCompleted: requestPaint()
            Connections { target: Theme; function onAccentNameChanged() { map.requestPaint() } }
            onPaint: {
                const c = getContext("2d"), w = width, h = height, a = Theme.accent
                const rgb = Math.round(a.r * 255) + "," + Math.round(a.g * 255) + "," + Math.round(a.b * 255)
                c.reset(); c.clearRect(0, 0, w, h)
                const s = Math.min(w / 360, h / 150), ox = (w - 360 * s) / 2, oy = (h - 150 * s) / 2
                const X = lon => ox + (lon + 180) * s, Y = lat => oy + (80 - lat) * s
                c.beginPath()
                for (const ring of (card.land.rings || [])) {
                    if (ring[1] < -58) continue               // Antarctica is left off the small map
                    c.moveTo(X(ring[0]), Y(ring[1]))
                    for (let i = 2; i < ring.length; i += 2) c.lineTo(X(ring[i]), Y(ring[i + 1]))
                    c.closePath()
                }
                c.fillStyle = "rgba(" + rgb + ",0.16)"; c.fill()
                c.strokeStyle = "rgba(" + rgb + ",0.22)"; c.lineWidth = 3; c.stroke()
                c.strokeStyle = "rgba(" + rgb + ",0.75)"; c.lineWidth = 0.7; c.stroke()
                // Events: quakes (warm), severe disasters (red / amber).
                for (const q of card.quakes) {
                    const r = 1 + Math.max(0, q.mag - 3) * 0.9
                    c.fillStyle = Theme.css(Theme.warm, 0.9); c.beginPath(); c.arc(X(q.lon), Y(q.lat), r, 0, Math.PI * 2); c.fill()
                }
                for (const i of card.items("alerts")) {
                    if (i.alert === "Green") continue
                    c.strokeStyle = i.alert === "Red" ? Theme.css(Theme.critical, 0.95) : Theme.css(Theme.warm, 0.9); c.lineWidth = 1.2
                    c.beginPath(); c.arc(X(i.lon), Y(i.lat), 3.2, 0, Math.PI * 2); c.stroke()
                }
            }
        }
        Column {
            x: map.width + 14; width: parent.width - x; anchors.verticalCenter: parent.verticalCenter; spacing: 7
            Repeater {
                model: card.rows
                delegate: Item {
                    required property var modelData
                    width: parent.width; height: 22
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: card.toneColour(modelData[2]) }
                    Text { id: rowLabel; x: 16; anchors.verticalCenter: parent.verticalCenter; text: modelData[0]; color: Theme.text; font.pixelSize: 12 }
                    Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: modelData[1]
                           width: parent.width - rowLabel.x - rowLabel.implicitWidth - 8; horizontalAlignment: Text.AlignRight; elide: Text.ElideLeft
                           color: modelData[2] ? card.toneColour(modelData[2]) : Theme.accent; font.pixelSize: 11 }
                }
            }
        }
    }
    Item {
        width: parent.width; height: 26
        Text { anchors.verticalCenter: parent.verticalCenter; text: "View details"; color: Theme.text; font.pixelSize: 13 }
        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: "›"; color: Theme.muted; font.pixelSize: 18 }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: card.go("atlas") }
    }
}
