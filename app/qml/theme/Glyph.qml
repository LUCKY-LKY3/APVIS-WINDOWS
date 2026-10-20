import QtQuick

// Crisp line icons drawn natively (no icon font or SVG plugin on the image).
// Technique carried over from the APVIS 7.0.1 HudGlyph; recoloured by theme.
Item {
    id: glyph
    property string kind: "core"
    property color stroke: Theme.accent
    property color accent: Theme.text
    implicitWidth: 20
    implicitHeight: 20
    onKindChanged: art.requestPaint()
    onStrokeChanged: art.requestPaint()

    Canvas {
        id: art
        anchors.fill: parent
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()
        onPaint: {
            const c = getContext("2d"), w = width, h = height, cx = w / 2, cy = h / 2, m = Math.min(w, h)
            c.clearRect(0, 0, w, h)
            c.strokeStyle = glyph.stroke; c.fillStyle = glyph.stroke
            c.lineWidth = Math.max(1.2, m * 0.075)
            c.lineCap = "round"; c.lineJoin = "round"
            const k = glyph.kind
            function line(x1, y1, x2, y2) { c.beginPath(); c.moveTo(w*x1, h*y1); c.lineTo(w*x2, h*y2); c.stroke() }
            function circle(x, y, r, fill) { c.beginPath(); c.arc(w*x, h*y, m*r, 0, Math.PI*2); fill ? c.fill() : c.stroke() }
            if (k === "apvis") {
                // The V3 mark as a line icon (as ApvisMark): an outer ring broken at the diagonals, six reactor
                // segments and a bright centre. (The faceted "A" was retired, owner 2026-10-09.)
                c.lineCap = "butt"
                c.lineWidth = Math.max(1.2, m * .07)
                for (let i = 0; i < 4; ++i) { const mid = i * Math.PI / 2; c.beginPath(); c.arc(cx, cy, m * .44, mid - .55, mid + .55); c.stroke() }
                c.lineWidth = Math.max(1.4, m * .085)
                for (let i = 0; i < 6; ++i) { const mid = i * Math.PI / 3 + Math.PI / 6; c.beginPath(); c.arc(cx, cy, m * .29, mid - .32, mid + .32); c.stroke() }
                c.fillStyle = glyph.accent; circle(.5, .5, .1, true)
            } else if (k === "game") {
                // A controller: body, d-pad, two buttons.
                c.beginPath(); c.moveTo(w*.22,h*.30); c.lineTo(w*.78,h*.30); c.quadraticCurveTo(w*.96,h*.30,w*.94,h*.56)
                c.lineTo(w*.90,h*.74); c.quadraticCurveTo(w*.86,h*.86,w*.74,h*.80); c.lineTo(w*.62,h*.68); c.lineTo(w*.38,h*.68)
                c.lineTo(w*.26,h*.80); c.quadraticCurveTo(w*.14,h*.86,w*.10,h*.74); c.lineTo(w*.06,h*.56)
                c.quadraticCurveTo(w*.04,h*.30,w*.22,h*.30); c.closePath(); c.stroke()
                line(.24,.49,.38,.49); line(.31,.42,.31,.56)
                circle(.66,.45,.035,true); circle(.74,.53,.035,true)
            } else if (k === "home") {
                c.beginPath(); c.moveTo(w*.14,h*.48); c.lineTo(cx,h*.14); c.lineTo(w*.86,h*.48); c.stroke()
                c.beginPath(); c.moveTo(w*.24,h*.42); c.lineTo(w*.24,h*.86); c.lineTo(w*.76,h*.86); c.lineTo(w*.76,h*.42); c.stroke()
                c.strokeRect(w*.42,h*.60,w*.16,h*.26)
            } else if (k === "mission") {
                circle(.5,.5,.34); circle(.5,.5,.16)
                line(.5,.04,.5,.20); line(.5,.80,.5,.96); line(.04,.5,.20,.5); line(.80,.5,.96,.5)
            } else if (k === "atlas") {
                circle(.5,.5,.38)
                c.beginPath(); c.ellipse(w*.33,h*.12,w*.34,h*.76); c.stroke()
                line(.12,.5,.88,.5); line(.18,.3,.82,.3); line(.18,.7,.82,.7)
            } else if (k === "notes") {
                c.beginPath(); c.moveTo(w*.22,h*.10); c.lineTo(w*.62,h*.10); c.lineTo(w*.80,h*.28); c.lineTo(w*.80,h*.90); c.lineTo(w*.22,h*.90); c.closePath(); c.stroke()
                line(.34,.44,.68,.44); line(.34,.60,.68,.60); line(.34,.76,.56,.76)
            } else if (k === "files") {
                c.beginPath(); c.moveTo(w*.10,h*.24); c.lineTo(w*.40,h*.24); c.lineTo(w*.48,h*.34); c.lineTo(w*.90,h*.34); c.lineTo(w*.90,h*.82); c.lineTo(w*.10,h*.82); c.closePath(); c.stroke()
            } else if (k === "apps") {
                for (let r = 0; r < 2; ++r) for (let col = 0; col < 2; ++col) c.strokeRect(w*(.14+col*.40), h*(.14+r*.40), w*.32, h*.32)
            } else if (k === "terminal") {
                c.strokeRect(w*.08,h*.14,w*.84,h*.72)
                c.beginPath(); c.moveTo(w*.22,h*.38); c.lineTo(w*.38,h*.50); c.lineTo(w*.22,h*.62); c.stroke(); line(.46,.64,.72,.64)
            } else if (k === "settings") {
                for (let i = 0; i < 8; ++i) { const a = i*Math.PI/4; c.beginPath(); c.moveTo(cx+Math.cos(a)*m*.30, cy+Math.sin(a)*m*.30); c.lineTo(cx+Math.cos(a)*m*.44, cy+Math.sin(a)*m*.44); c.stroke() }
                circle(.5,.5,.26); circle(.5,.5,.10)
            } else if (k === "ask") {
                c.beginPath(); c.moveTo(w*.14,h*.20); c.lineTo(w*.86,h*.20); c.lineTo(w*.86,h*.66); c.lineTo(w*.46,h*.66); c.lineTo(w*.26,h*.86); c.lineTo(w*.28,h*.66); c.lineTo(w*.14,h*.66); c.closePath(); c.stroke()
            } else if (k === "search") {
                circle(.42,.42,.26); line(.62,.62,.88,.88)
            } else if (k === "wifi") {
                for (let i = 0; i < 3; ++i) { c.beginPath(); c.arc(cx, h*.82, m*(.18+i*.2), Math.PI*1.25, Math.PI*1.75); c.stroke() }
                circle(.5,.82,.06,true)
            } else if (k === "plus") {
                line(.5,.16,.5,.84); line(.16,.5,.84,.5)
            } else if (k === "chart") {
                line(.14,.86,.86,.86); c.strokeRect(w*.20,h*.56,w*.12,h*.30); c.strokeRect(w*.44,h*.36,w*.12,h*.50); c.strokeRect(w*.68,h*.16,w*.12,h*.70)
            } else if (k === "grid") {
                for (let r = 0; r < 2; ++r) for (let col = 0; col < 2; ++col) circle(.30 + col * .40, .30 + r * .40, .14)
            } else if (k === "chip") {
                c.strokeRect(w*.26,h*.26,w*.48,h*.48); c.strokeRect(w*.40,h*.40,w*.20,h*.20)
                for (let i = 0; i < 3; ++i) { const t = .34 + i * .16; line(t,.10,t,.26); line(t,.74,t,.90); line(.10,t,.26,t); line(.74,t,.90,t) }
            } else if (k === "clock") {
                circle(.5,.5,.38); line(.5,.5,.5,.26); line(.5,.5,.68,.60)
            } else if (k === "gear") {
                circle(.5,.5,.16)
                for (let i = 0; i < 8; ++i) { const a = i * Math.PI / 4; c.beginPath(); c.moveTo(cx + Math.cos(a) * m * .26, cy + Math.sin(a) * m * .26)
                    c.lineTo(cx + Math.cos(a) * m * .40, cy + Math.sin(a) * m * .40); c.stroke() }
                circle(.5,.5,.28)
            } else if (k === "wired") {
                c.strokeRect(w*.30,h*.14,w*.40,h*.30); line(.5,.44,.5,.66); line(.2,.66,.8,.66); line(.2,.66,.2,.86); line(.8,.66,.8,.86); line(.5,.66,.5,.86)
            } else if (k === "volume") {
                c.beginPath(); c.moveTo(w*.12,h*.38); c.lineTo(w*.30,h*.38); c.lineTo(w*.52,h*.18); c.lineTo(w*.52,h*.82); c.lineTo(w*.30,h*.62); c.lineTo(w*.12,h*.62); c.closePath(); c.stroke()
                c.beginPath(); c.arc(w*.52,cy,m*.22,-.8,.8); c.stroke(); c.beginPath(); c.arc(w*.52,cy,m*.38,-.8,.8); c.stroke()
            } else if (k === "battery") {
                c.strokeRect(w*.08,h*.28,w*.76,h*.44); c.fillRect(w*.86,h*.40,w*.08,h*.20)
            } else if (k === "cpu") {
                c.strokeRect(w*.26,h*.26,w*.48,h*.48); c.strokeRect(w*.40,h*.40,w*.20,h*.20)
                for (let i = 0; i < 3; ++i) { const t = .34+i*.16; line(t,.10,t,.26); line(t,.74,t,.90); line(.10,t,.26,t); line(.74,t,.90,t) }
            } else if (k === "memory") {
                c.strokeRect(w*.10,h*.30,w*.80,h*.40)
                for (let i = 0; i < 4; ++i) c.strokeRect(w*(.18+i*.18), h*.40, w*.10, h*.20)
                for (let i = 0; i < 6; ++i) line(.16+i*.136,.70,.16+i*.136,.84)
            } else if (k === "storage") {
                c.beginPath(); c.ellipse(w*.16,h*.12,w*.68,h*.22); c.stroke()
                line(.16,.23,.16,.77); line(.84,.23,.84,.77)
                c.beginPath(); c.moveTo(w*.16,h*.77); c.quadraticCurveTo(cx,h*.99,w*.84,h*.77); c.stroke()
                c.beginPath(); c.moveTo(w*.16,h*.50); c.quadraticCurveTo(cx,h*.72,w*.84,h*.50); c.stroke()
            } else if (k === "device") {
                c.strokeRect(w*.10,h*.16,w*.80,h*.52); line(.5,.68,.5,.82); line(.30,.84,.70,.84)
            } else if (k === "brain") {
                c.beginPath(); c.arc(w*.38,h*.40,m*.22,Math.PI*.55,Math.PI*1.9); c.stroke()
                c.beginPath(); c.arc(w*.62,h*.40,m*.22,Math.PI*1.1,Math.PI*.45); c.stroke()
                line(.5,.20,.5,.84)
                c.beginPath(); c.arc(w*.38,h*.64,m*.20,Math.PI*.4,Math.PI*1.2); c.stroke()
                c.beginPath(); c.arc(w*.62,h*.64,m*.20,Math.PI*1.8,Math.PI*.6); c.stroke()
            } else if (k === "check") {
                c.beginPath(); c.moveTo(w*.16,h*.52); c.lineTo(w*.40,h*.76); c.lineTo(w*.86,h*.26); c.stroke()
            } else if (k === "activity") {
                c.beginPath(); c.moveTo(w*.06,cy); c.lineTo(w*.30,cy); c.lineTo(w*.40,h*.22); c.lineTo(w*.54,h*.80); c.lineTo(w*.64,h*.40); c.lineTo(w*.72,cy); c.lineTo(w*.94,cy); c.stroke()
            } else if (k === "plane") {
                c.beginPath(); c.moveTo(cx,h*.06); c.lineTo(w*.56,h*.38); c.lineTo(w*.92,h*.56); c.lineTo(w*.92,h*.64); c.lineTo(w*.56,h*.54)
                c.lineTo(w*.54,h*.80); c.lineTo(w*.66,h*.90); c.lineTo(w*.34,h*.90); c.lineTo(w*.46,h*.80); c.lineTo(w*.44,h*.54)
                c.lineTo(w*.08,h*.64); c.lineTo(w*.08,h*.56); c.lineTo(w*.44,h*.38); c.closePath(); c.stroke()
            } else if (k === "more") {
                for (let r = 0; r < 2; ++r) for (let col = 0; col < 2; ++col) circle(.30+col*.40, .30+r*.40, .12)
            } else if (k === "power") {
                c.beginPath(); c.arc(cx, cy*1.06, m*.34, -Math.PI*0.32, Math.PI*1.32); c.stroke()
                line(.5,.10,.5,.50)
            } else if (k === "moon") {
                c.beginPath(); c.arc(cx, cy, m*.34, Math.PI*0.35, Math.PI*1.65); c.stroke()
                c.beginPath(); c.arc(cx+m*.12, cy-m*.02, m*.26, Math.PI*0.62, Math.PI*1.38, true); c.stroke()
            } else if (k === "restart") {
                c.beginPath(); c.arc(cx, cy, m*.32, -Math.PI*0.35, Math.PI*1.45); c.stroke()
                c.beginPath(); c.moveTo(w*.64,h*.12); c.lineTo(w*.78,h*.24); c.lineTo(w*.62,h*.32); c.stroke()
            } else if (k === "logout") {
                c.beginPath(); c.moveTo(w*.46,h*.16); c.lineTo(w*.18,h*.16); c.lineTo(w*.18,h*.84); c.lineTo(w*.46,h*.84); c.stroke()
                line(.38,.5,.86,.5)
                c.beginPath(); c.moveTo(w*.70,h*.34); c.lineTo(w*.86,h*.5); c.lineTo(w*.70,h*.66); c.stroke()
            } else if (k === "key") {
                circle(.32,.5,.17)
                line(.49,.5,.88,.5); line(.74,.5,.74,.66); line(.86,.5,.86,.62)
            } else if (k === "screen") {
                c.strokeRect(w*.12, h*.18, w*.76, h*.50)
                line(.38,.84,.62,.84); line(.5,.68,.5,.84)
            } else if (k === "timer") {
                circle(.5,.55,.32)
                line(.5,.55,.5,.36); line(.5,.55,.64,.62); line(.40,.10,.60,.10)
            } else {
                for (let i = 0; i < 6; ++i) { const a = i*Math.PI/3, x = cx+Math.cos(a)*m*.34, y = cy+Math.sin(a)*m*.34; c.beginPath(); c.moveTo(cx,cy); c.lineTo(x,y); c.stroke(); c.beginPath(); c.arc(x,y,m*.055,0,Math.PI*2); c.fill() }
                c.fillStyle = glyph.accent; circle(.5,.5,.09,true)
            }
        }
    }
}
