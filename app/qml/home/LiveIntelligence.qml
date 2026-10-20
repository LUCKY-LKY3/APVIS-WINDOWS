import QtQuick
import "../theme"

// OSIRIS at a glance: the last Atlas aviation snapshot on a small UK map.
// It never fetches by itself and never pretends to be live: while Atlas is
// polling it says LIVE; otherwise it shows how old the snapshot is and dims.
Item {
    id: card
    property var info: ({})            // shell.atlas
    property string aircraftJson: "[]"
    property string mapJson: "{}"
    property bool atlasOpen: false
    property real now: Date.now()
    signal openAtlas()

    readonly property var planes: JSON.parse(aircraftJson)
    readonly property var map: JSON.parse(mapJson)
    readonly property real ageS: info.fetched_at ? Math.max(0, (now - Date.parse(info.fetched_at)) / 1000) : -1
    readonly property bool live: atlasOpen && info.status === "live"
    readonly property bool hasData: planes.length > 0 && ageS >= 0
    onPlanesChanged: mini.requestPaint()
    onLiveChanged: mini.requestPaint()
    Timer { interval: 15000; running: card.visible; repeat: true; triggeredOnStart: true; onTriggered: card.now = Date.now() }
    onInfoChanged: now = Date.now()

    function ago(s) { return s < 60 ? Math.round(s) + " s" : s < 3600 ? Math.round(s / 60) + " min" : Math.round(s / 3600) + " h" }

    implicitHeight: 150
    Canvas {
        id: mini
        x: 0; y: 0; width: parent.width * 0.44; height: parent.height
        readonly property real latMin: 49.6
        readonly property real latMax: 59.2
        readonly property real lonMin: -10.8
        readonly property real lonMax: 2.2
        readonly property real k: Math.cos(55 * Math.PI / 180)
        readonly property real s: Math.min(width / ((lonMax - lonMin) * k), height / (latMax - latMin))
        function px(lon) { return (width - (lonMax - lonMin) * k * s) / 2 + (lon - lonMin) * k * s }
        function py(lat) { return (height - (latMax - latMin) * s) / 2 + (latMax - lat) * s }
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()
        onPaint: {
            const c = getContext("2d"); c.reset(); c.clearRect(0, 0, width, height)
            c.strokeStyle = Theme.muted; c.globalAlpha = .7; c.lineWidth = .8
            const rings = card.map.rings || []
            c.beginPath()
            for (let r = 0; r < rings.length; ++r) {
                const ring = rings[r]; c.moveTo(px(ring[0]), py(ring[1]))
                for (let i = 2; i < ring.length; i += 2) c.lineTo(px(ring[i]), py(ring[i + 1]))
            }
            c.stroke()
            c.globalAlpha = card.live ? .95 : .45
            for (let i = 0; i < card.planes.length; ++i) {
                const p = card.planes[i]
                if (p[7]) continue            // skip aircraft on the ground
                c.fillStyle = p[11] ? Theme.attention : Theme.accent
                c.beginPath(); c.arc(px(p[5]), py(p[4]), 1.3, 0, Math.PI * 2); c.fill()
            }
            c.globalAlpha = 1
        }
    }
    Column {
        x: mini.width + 14; width: parent.width - x; spacing: 6
        anchors.verticalCenter: parent.verticalCenter
        Row {
            spacing: 8
            Glyph { width: 14; height: 14; kind: "plane"; stroke: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
            Text { text: "Flights over the UK"; color: Theme.text; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
        }
        Text {
            text: card.planes.filter(p => !p[7]).length + " airborne"
            color: Theme.text; font.pixelSize: 20
        }
        Text {
            width: parent.width; wrapMode: Text.WordWrap; font.pixelSize: 10; font.letterSpacing: 1
            color: card.live ? Theme.accent : Theme.attention
            text: card.live ? "LIVE · updated " + card.ago(card.info.age_s || 0) + " ago"
                            : "LAST SEEN " + card.ago(card.ageS) + " AGO · NOT LIVE"
        }
        Text { width: parent.width; text: (card.info.source || "public ADS-B") + " · " + (card.info.licence || ""); color: Theme.muted; font.pixelSize: 9; elide: Text.ElideRight }
    }
    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: card.openAtlas() }
    Accessible.role: Accessible.Button
    Accessible.name: "Flights over the UK: " + planes.filter(p => !p[7]).length + " airborne, " +
                     (live ? "live" : "last seen " + ago(ageS) + " ago, not live") + ". Open Atlas."
}
