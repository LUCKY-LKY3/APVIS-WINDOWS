import QtQuick
import "../theme"

Item {
    id: root

    // standby | gaming | mission | fusion | atlas | answer
    property string mode: "standby"
    property real phase: 0
    property real lastPaintPhase: -10
    property int particleBudget: 1800
    property real transitionProgress: 1
    property string previousMode: "standby"
    property string renderedMode: "standby"
    property real centerOffsetX: 0
    property bool atlasLocationAvailable: false
    property real atlasLatitude: 0
    property real atlasLongitude: 0
    // Ported from APVIS 7.0.1 (V7NeuralFabric.qml); colours now come from the theme.
    property color cobalt: Theme.coreTint
    property color coolWhite: Theme.coreHighlight
    property color amber: Theme.attention
    property color deepBlue: Theme.ink
    property bool reducedMotion: false
    // Renderer-independent APVIS visual state. The bridge supplies targets;
    // these properties interpolate locally without a Python/React frame loop.
    property string particleState: "idle"
    property real energy: .34
    property real activity: .20
    property real coreIntensity: .44
    property real density: .72
    property real rotationSpeed: .18
    property real orbitSpeed: .22
    property real turbulence: .14
    property real pulseStrength: .12
    property real expansion: 0
    property real instability: 0
    property real qualityScale: 1
    // Deliberately lightweight continent silhouettes: enough geography for a
    // recognisable particle Earth without shipping a heavy map asset into the
    // renderer.
    property var atlasContinents: [
        [[-168,70],[-140,72],[-126,57],[-112,49],[-96,52],[-83,28],[-98,17],[-117,31],[-128,49],[-150,58]],
        [[-82,12],[-68,8],[-52,-2],[-36,-22],[-54,-55],[-72,-43],[-78,-12]],
        [[-73,60],[-22,59],[-18,82],[-52,84]],
        [[-11,36],[2,44],[18,39],[32,47],[42,58],[25,71],[-8,71]],
        [[-18,36],[14,37],[42,12],[50,-11],[31,-35],[10,-35],[-7,-5]],
        [[30,40],[44,63],[92,77],[180,66],[145,45],[123,7],[101,2],[73,19],[55,28]],
        [[35,30],[56,27],[71,8],[78,7],[91,22],[77,34],[58,17],[45,13]],
        [[112,-11],[154,-10],[153,-38],[126,-44],[112,-27]],
        [[130,31],[146,47],[151,43],[137,29]]
    ]
    // Cross-fades draw two complete scenes. Keep their combined temporary
    // budget below the settled scene so a transformation cannot double the
    // OptiPlex render load.
    readonly property real transitionDensity: 0.36

    readonly property real aperture: mode === "mission" || mode === "answer" ? 0.34 : 0.08
    readonly property bool active: visible && width > 40 && height > 40

    onPhaseChanged: {
        const threshold = mode === "mission" || mode === "answer" ? 1.65
                        : mode === "standby" ? 1.75 : 0.92
        if (Math.abs(phase - lastPaintPhase) >= threshold) {
            lastPaintPhase = phase
            fabric.requestPaint()
        }
    }
    onModeChanged: {
        if (mode === renderedMode) return
        previousMode = renderedMode
        renderedMode = mode
        transitionProgress = 0
        modeTransition.restart()
        fabric.requestPaint()
    }
    onTransitionProgressChanged: fabric.requestPaint()
    onCenterOffsetXChanged: fabric.requestPaint()
    onAtlasLatitudeChanged: fabric.requestPaint()
    onAtlasLongitudeChanged: fabric.requestPaint()
    onParticleBudgetChanged: fabric.requestPaint()
    onWidthChanged: fabric.requestPaint()
    onHeightChanged: fabric.requestPaint()

    Behavior on centerOffsetX { NumberAnimation { duration: 520; easing.type: Easing.InOutCubic } }
    Behavior on energy { NumberAnimation { duration: 520; easing.type: Easing.InOutCubic } }
    Behavior on activity { NumberAnimation { duration: 460; easing.type: Easing.InOutCubic } }
    Behavior on coreIntensity { NumberAnimation { duration: 580; easing.type: Easing.InOutCubic } }
    Behavior on density { NumberAnimation { duration: 640; easing.type: Easing.InOutCubic } }
    Behavior on rotationSpeed { NumberAnimation { duration: 720; easing.type: Easing.InOutCubic } }
    Behavior on orbitSpeed { NumberAnimation { duration: 640; easing.type: Easing.InOutCubic } }
    Behavior on turbulence { NumberAnimation { duration: 420; easing.type: Easing.InOutCubic } }
    Behavior on pulseStrength { NumberAnimation { duration: 420; easing.type: Easing.InOutCubic } }
    Behavior on expansion { NumberAnimation { duration: 560; easing.type: Easing.OutCubic } }
    Behavior on instability { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
    NumberAnimation {
        id: modeTransition
        target: root
        property: "transitionProgress"
        from: 0
        to: 1
        duration: root.reducedMotion ? 1 : 760
        easing.type: Easing.InOutCubic
    }

    // High-density standby mass is cached once. The live Canvas above it only
    // animates the brighter foreground particles, keeping the OptiPlex fluid
    // without sacrificing the reference image's dense neural-fabric look.
    Canvas {
        id: standbyCache
        anchors.fill: parent
        visible: root.mode === "standby" || root.mode === "gaming"
        opacity: .72 + root.energy * .26
        rotation: root.reducedMotion ? 0 : root.phase * (.025 + root.rotationSpeed * .11)
        scale: root.reducedMotion ? 1 : 1 + root.expansion * .055 + Math.sin(root.phase * (.018 + root.activity * .038)) * (.0025 + root.pulseStrength * .009)
        transformOrigin: Item.Center
        antialiasing: true
        renderTarget: Canvas.FramebufferObject
        function fract(value) { return value - Math.floor(value) }
        function hash(index, seed) { return fract(Math.sin(index * 91.713 + seed * 17.17) * 43758.5453) }
        function point(index, count, span, cx, cy) {
            const golden=2.399963229728653, unit=(index+.5)/count, z=1-2*unit
            const radial=Math.sqrt(Math.max(0,1-z*z)), angle=index*golden
            const depth=radial*Math.sin(angle), scale=.76+.24*(depth+1)*.5
            return { x:cx+radial*Math.cos(angle)*span*scale, y:cy+z*span*.92, depth:depth, angle:angle, z:z }
        }
        onPaint: {
            if (width < 40 || height < 40) return
            const c=getContext("2d"), cx=width*.5, cy=height*.49, span=Math.min(width,height)*.47, count=5800
            c.clearRect(0,0,width,height); c.save(); c.globalCompositeOperation="lighter"
            for(let i=0;i<count;++i){
                const p=point(i,count,span,cx,cy), dx=p.x-cx, dy=(p.y-cy)/.92, edge=Math.min(1,Math.sqrt(dx*dx+dy*dy)/span)
                const ridge=Math.pow(Math.max(0,Math.sin(p.angle*1.72+p.z*10.5)+.13),5.2)
                const perspective=.58+.42*(p.depth+1)*.5
                const alpha=Math.min(.98,(.16+edge*.46+ridge*.64)*perspective)
                c.fillStyle=i%97===0?"rgba(255,166,55,.9)":"rgba(42,143,255,"+alpha+")"
                c.beginPath(); c.arc(p.x,p.y,(.42+edge*.66+ridge*.72)*perspective,0,Math.PI*2); c.fill()
                if(i%113===0){
                    const glow=c.createRadialGradient(p.x,p.y,0,p.x,p.y,7)
                    glow.addColorStop(0,i%226===0?"rgba(255,190,102,.9)":"rgba(205,239,255,.92)")
                    glow.addColorStop(.22,"rgba(68,164,255,.48)");glow.addColorStop(1,"rgba(21,91,220,0)")
                    c.fillStyle=glow;c.beginPath();c.arc(p.x,p.y,7,0,Math.PI*2);c.fill()
                }
            }
            c.lineWidth=.48
            for(let i=0;i<count;i+=13){
                const a=point(i,count,span,cx,cy), b=point((i*7+113)%count,count,span,cx,cy)
                if(a.depth>-.26&&b.depth>-.26){c.strokeStyle="rgba(47,133,241,.20)";c.beginPath();c.moveTo(a.x,a.y);c.lineTo(b.x,b.y);c.stroke()}
            }
            // Dense neural streams sweep across the shell in irregular bands.
            // They are cached with the background, so the richer reference
            // silhouette does not increase the per-frame particle budget.
            for(let ribbon=0;ribbon<7;++ribbon){
                const rotation=-1.02+ribbon*.31, cr=Math.cos(rotation), sr=Math.sin(rotation)
                const rx=span*(.76+ribbon*.028), ry=span*(.42+(ribbon%3)*.105)
                for(let step=0;step<230;++step){
                    const t=step*Math.PI*2/230+ribbon*.47
                    const warp=1+Math.sin(t*3.0+ribbon*1.7)*.055
                    const px=Math.cos(t)*rx*warp, py=Math.sin(t)*ry+Math.sin(t*5+ribbon)*span*.012
                    const x=cx+px*cr-py*sr, y=cy+px*sr+py*cr
                    const front=.48+.52*Math.max(0,Math.sin(t+ribbon*.63))
                    c.fillStyle=step%71===0?"rgba(255,175,74,.94)":"rgba(48,154,255,"+(.20+front*.54)+")"
                    c.beginPath();c.arc(x,y,.52+front*.82,0,Math.PI*2);c.fill()
                    if(step%19===0){c.strokeStyle="rgba(100,190,255,.28)";c.lineWidth=.55;c.beginPath();c.moveTo(x,y);c.lineTo(cx+(x-cx)*.965,cy+(y-cy)*.965);c.stroke()}
                }
            }
            // The centre is deliberately made from the same field as the
            // globe, rather than a separate "reactor" drawn over the top.
            // This creates a natural concentration of routes with no hard
            // circular object competing with the world silhouette.
            const innerNodes=[]
            for(let i=0;i<920;++i){
                const seed=hash(i,18.7), angle=i*2.3999632297+Math.sin(i*.13)*.18
                const r=span*(.055+.43*Math.pow(seed,.72))
                const squash=.72+.16*Math.sin(i*.071)
                const x=cx+Math.cos(angle)*r*(.94+.06*Math.sin(i*.19))
                const y=cy+Math.sin(angle)*r*squash
                const alpha=.10+.28*(r/span)+((i%47===0)?.22:0)
                c.fillStyle=i%173===0?"rgba(255,164,58,.68)":"rgba(65,157,255,"+alpha+")"
                c.beginPath();c.arc(x,y,.34+(r/span)*.64+(i%47===0?1.0:0),0,Math.PI*2);c.fill()
                if(i%23===0) innerNodes.push({x:x,y:y})
            }
            c.lineWidth=.42
            for(let i=0;i<innerNodes.length;++i){
                const a=innerNodes[i], b=innerNodes[(i*5+11)%innerNodes.length]
                c.strokeStyle="rgba(68,151,245,.13)";c.beginPath();c.moveTo(a.x,a.y);c.lineTo(b.x,b.y);c.stroke()
            }
            // Engineered latitude bands and orbit rails make the cached mass
            // read as a particle instrument rather than a dark wire sphere.
            for(let band=-4;band<=4;++band){
                const y=cy+band*span*.108, rx=span*Math.sqrt(Math.max(.10,1-band*band*.035)), ry=span*(.105+Math.abs(band)*.012)
                c.strokeStyle=band===0?"rgba(76,169,255,.42)":"rgba(50,132,238,.22)"; c.lineWidth=band===0?1.1:.62
                c.beginPath()
                for(let step=0;step<=72;++step){const a=step*Math.PI*2/72,x=cx+Math.cos(a)*rx,y2=y+Math.sin(a)*ry;if(step===0)c.moveTo(x,y2);else c.lineTo(x,y2)}
                c.stroke()
            }
            for(let orbit=0;orbit<4;++orbit){
                const radius=span*(1.02+orbit*.045), start=.55+orbit*1.21
                c.strokeStyle=orbit===2?"rgba(255,166,56,.43)":"rgba(75,155,246,.29)";c.lineWidth=orbit===2?.95:.65
                c.beginPath();c.arc(cx,cy,radius,start,start+1.18);c.stroke()
                const nx=cx+Math.cos(start+1.18)*radius, ny=cy+Math.sin(start+1.18)*radius
                c.fillStyle=orbit===2?"rgba(255,176,73,.92)":"rgba(96,183,255,.9)";c.beginPath();c.arc(nx,ny,2.3,0,Math.PI*2);c.fill()
            }
            c.restore()

            // Physical depth: a cool highlight sits forward-left while the
            // far rim falls into black, turning the particle mass into a sphere.
            c.save(); c.globalCompositeOperation="source-over"
            const shade=c.createRadialGradient(cx-span*.18,cy-span*.18,span*.18,cx,cy,span*1.05)
            shade.addColorStop(0,"rgba(0,0,0,0)");shade.addColorStop(.62,"rgba(0,1,7,.02)");shade.addColorStop(1,"rgba(0,2,12,.48)")
            c.fillStyle=shade;c.beginPath();c.arc(cx,cy,span*1.01,0,Math.PI*2);c.fill()
            c.globalCompositeOperation="lighter"
            const light=c.createRadialGradient(cx-span*.30,cy-span*.32,0,cx-span*.30,cy-span*.32,span*.52)
            light.addColorStop(0,"rgba(104,191,255,.12)");light.addColorStop(.45,"rgba(35,126,255,.035)");light.addColorStop(1,"rgba(0,0,0,0)")
            c.fillStyle=light;c.beginPath();c.arc(cx-span*.30,cy-span*.32,span*.52,0,Math.PI*2);c.fill()

            // Segmented outer instrumentation and target nodes mirror the
            // reference without joining the old off-axis loop trajectories.
            for(let rail=0;rail<8;++rail){
                const radius=span*(1.035+rail*.031)
                c.strokeStyle=rail===3?"rgba(210,233,255,.52)":"rgba(63,145,245,"+(.15+rail*.018)+")"
                c.lineWidth=rail===3?1.05:.62
                for(let segment=0;segment<32;++segment){
                    if((segment+rail*3)%7===0 || (segment*5+rail)%11===0) continue
                    const a=segment*Math.PI*2/32+rail*.071
                    c.beginPath();c.arc(cx,cy,radius,a,a+.108+(rail%3)*.018);c.stroke()
                }
            }
            for(let node=0;node<5;++node){
                const a=-.62+node*1.37, radius=span*(1.075+(node%2)*.105), x=cx+Math.cos(a)*radius, y=cy+Math.sin(a)*radius
                c.strokeStyle=node===2?"rgba(255,174,67,.84)":"rgba(91,177,255,.82)";c.lineWidth=1
                c.beginPath();c.arc(x,y,10,0,Math.PI*2);c.stroke();c.beginPath();c.arc(x,y,4.2,0,Math.PI*2);c.stroke()
                c.fillStyle=node===2?"rgba(255,178,75,.96)":"rgba(170,222,255,.94)";c.beginPath();c.arc(x,y,1.65,0,Math.PI*2);c.fill()
                c.strokeStyle="rgba(68,139,227,.36)";c.beginPath();c.arc(cx,cy,radius,a-.12,a+.12);c.stroke()
            }
            c.restore()
        }
        Component.onCompleted: requestPaint(); onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
    }

    Canvas {
        id: fabric
        anchors.fill: parent
        antialiasing: true
        renderTarget: Canvas.FramebufferObject

        function fract(value) { return value - Math.floor(value) }
        function hash(index, seed) { return fract(Math.sin(index * 91.713 + seed * 17.17) * 43758.5453) }

        // Qt's Canvas ellipse rotation is inconsistent between the offscreen
        // and XCB renderers used by the OptiPlex. Build rotated trajectories
        // explicitly so every orbit remains centred on the Neural Fabric.
        function strokeTrajectory(ctx, cx, cy, rx, ry, rotation, start, end) {
            const steps = 38
            const cosRotation = Math.cos(rotation)
            const sinRotation = Math.sin(rotation)
            ctx.beginPath()
            for (let step = 0; step <= steps; ++step) {
                const angle = start + (end - start) * step / steps
                const px = Math.cos(angle) * rx
                const py = Math.sin(angle) * ry
                const x = cx + px * cosRotation - py * sinRotation
                const y = cy + px * sinRotation + py * cosRotation
                if (step === 0) ctx.moveTo(x, y)
                else ctx.lineTo(x, y)
            }
            ctx.stroke()
        }

        function dot(ctx, x, y, radius, alpha, warm) {
            ctx.fillStyle = warm ? "rgba(255,166,62," + alpha + ")"
                                 : "rgba(42,151,255," + alpha + ")"
            ctx.beginPath()
            ctx.arc(x, y, radius, 0, Math.PI * 2)
            ctx.fill()
        }

        function dataSpark(ctx, x, y, radius, alpha) {
            const glow = ctx.createRadialGradient(x, y, 0, x, y, radius * 3.2)
            glow.addColorStop(0, "rgba(236,247,255," + alpha + ")")
            glow.addColorStop(.24, "rgba(101,180,255," + (alpha * .62) + ")")
            glow.addColorStop(1, "rgba(18,91,205,0)")
            ctx.fillStyle = glow
            ctx.beginPath(); ctx.arc(x, y, radius * 3.2, 0, Math.PI * 2); ctx.fill()
        }

        function standbyPoint(index, count, rotation, span, cx, cy) {
            const golden = 2.399963229728653
            const unit = (index + 0.5) / count
            const z = 1 - 2 * unit
            const radial = Math.sqrt(Math.max(0, 1 - z * z))
            const angle = index * golden + rotation
            const x3 = radial * Math.cos(angle)
            const depth = radial * Math.sin(angle)
            const scale = 0.76 + 0.24 * (depth + 1) * 0.5
            return {
                x: cx + x3 * span * scale,
                y: cy + z * span * 0.92,
                depth: depth,
            }
        }

        function drawStandby(ctx, cx, cy, span, count, time) {
            const golden = 2.399963229728653
            const rotation = time * (.0007 + root.orbitSpeed * .0032)
            const statePulse = .5 + .5 * Math.sin(time * (.0024 + root.activity * .006))
            const shellGlow = ctx.createRadialGradient(cx, cy, span * 0.52, cx, cy, span * 1.05)
            shellGlow.addColorStop(0, "rgba(3,15,38,0.015)")
            shellGlow.addColorStop(0.68, "rgba(8,48,122," + (.025 + root.energy * .055) + ")")
            shellGlow.addColorStop(0.86, "rgba(38,132,255," + (.08 + root.energy * .17) + ")")
            shellGlow.addColorStop(1, "rgba(0,0,0,0)")
            ctx.fillStyle = shellGlow; ctx.beginPath(); ctx.arc(cx, cy, span * 1.05, 0, Math.PI * 2); ctx.fill()
            for (let i = 0; i < count; ++i) {
                const unit = (i + 0.5) / count
                const z = 1 - 2 * unit
                const radial = Math.sqrt(Math.max(0, 1 - z * z))
                const angle = i * golden + rotation
                const x3 = radial * Math.cos(angle)
                const y3 = z
                const depth = radial * Math.sin(angle)
                const scale = 0.76 + 0.24 * (depth + 1) * 0.5
                const noise = root.reducedMotion ? 0 : Math.sin(i * 1.71 + time * .007) * root.turbulence * 2.2
                const x = cx + x3 * span * scale + noise * (1 - Math.abs(z))
                const y = cy + y3 * span * 0.92 + Math.cos(i * .93 + time * .006) * root.instability * 2.4
                const edge = Math.pow(Math.min(1, Math.sqrt(x3 * x3 + y3 * y3)), 1.8)
                const pulse = 0.76 + root.pulseStrength * Math.sin(time * 0.005 + i * 0.37)
                const perspectiveAlpha = .48 + .52 * (depth + 1) * .5
                dot(ctx, x, y, 0.48 + (1.0 + root.energy * .25) * edge * scale, (0.24 + 0.67 * edge) * pulse * perspectiveAlpha, i % 127 === 0)
                if (i % 2 === 0)
                    dot(ctx, cx + (x - cx) * .986 + Math.sin(i * .41) * 1.4,
                        cy + (y - cy) * .986 + Math.cos(i * .37) * 1.4,
                        .34 + edge * .28, .14 + edge * .16, i % 194 === 0)
                if (i % 83 === 0)
                    dataSpark(ctx, x, y, 1.0 + edge * .72, .54 + .26 * pulse)
                if (i % 3 === 0) {
                    const innerScale = 0.16 + 0.72 * Math.pow(hash(i, 12.4), 0.55)
                    const drift = Math.sin(time * 0.003 + i * 0.17) * 2.2
                    dot(ctx, cx + x3 * span * innerScale + drift, cy + y3 * span * 0.90 * innerScale,
                        0.42 + hash(i, 7.8) * 0.78, 0.22 + hash(i, 3.4) * 0.40, i % 379 === 0)
                }
            }
            ctx.lineWidth = 0.55
            for (let i = 0; i < count; i += 17) {
                const source = standbyPoint(i, count, rotation, span, cx, cy)
                const target = standbyPoint((i * 7 + 113) % count, count, rotation, span, cx, cy)
                if (source.depth > -0.35 && target.depth > -0.35) {
                    ctx.strokeStyle = "rgba(43,126,238,0.22)"
                    ctx.beginPath(); ctx.moveTo(source.x, source.y); ctx.lineTo(target.x, target.y); ctx.stroke()
                }
            }
            ctx.strokeStyle = "rgba(52,138,255,0.22)"
            ctx.lineWidth = 0.7
            for (let ring = 0; ring < 6; ++ring) {
                const tilt = -0.92 + ring * 0.34 + rotation * (ring % 2 ? -0.22 : 0.18)
                strokeTrajectory(ctx, cx, cy, span * (0.90 + ring * 0.024), span * (0.55 + (ring % 3) * 0.14), tilt, 0.10 + ring * .08, Math.PI * (1.46 + ring * .045))
            }
            // Full centred meridians preserve a spherical engineered silhouette
            // without reintroducing the old off-axis loop-de-loop artifact.
            for (let trace = 0; trace < 5; ++trace) {
                const traceAngle = rotation * (trace % 2 ? -0.18 : 0.15) + trace * 0.61
                ctx.strokeStyle = trace === 3 ? "rgba(255,155,48,0.18)" : "rgba(49,137,255,0.12)"
                ctx.lineWidth = trace === 3 ? 0.75 : 0.5
                strokeTrajectory(ctx, cx, cy, span * .94, span * (.69 + (trace % 2) * .12), traceAngle, 0, Math.PI * 2)
            }

            // A volumetric core made from the fabric itself: layered dust,
            // counter-rotating micro-orbits and a restrained energy well.
            const well = ctx.createRadialGradient(cx, cy, 0, cx, cy, span * .31)
            well.addColorStop(0, "rgba(224,244,255," + (.20 + root.coreIntensity * .36) + ")")
            well.addColorStop(.08, "rgba(52,150,255," + (.17 + root.coreIntensity * .23) + ")")
            well.addColorStop(.36, "rgba(10,62,160," + (.05 + root.energy * .08) + ")")
            well.addColorStop(1, "rgba(0,0,0,0)")
            ctx.fillStyle=well;ctx.beginPath();ctx.arc(cx,cy,span*.31,0,Math.PI*2);ctx.fill()
            const innerCount=Math.max(90,Math.floor(count*.42))
            for(let i=0;i<innerCount;++i){
                const depth=hash(i,31.7)*2-1, radial=Math.pow(hash(i,14.9),1.35)
                const angle=i*golden-rotation*(1.5+root.rotationSpeed)+depth*.7
                const radius=span*(.035+radial*.29)*(1+root.expansion*.15)
                const x=cx+Math.cos(angle)*radius*(.72+.28*(depth+1)*.5)
                const y=cy+Math.sin(angle)*radius*.68
                dot(ctx,x,y,.38+radial*.7,(.12+root.coreIntensity*.36)*(1-radial*.35),i%181===0)
            }

            // Meaningful state micro-interactions; no generic perpetual flash.
            if(root.particleState==="working"){
                for(let lane=0;lane<7;++lane){
                    const a=-.55+lane*.18+Math.sin(time*.006+lane)*.025
                    const length=span*(.42+.46*statePulse)
                    ctx.strokeStyle=lane===3?"rgba(225,244,255,.62)":"rgba(47,145,255,.28)"
                    ctx.lineWidth=lane===3?1.25:.62;ctx.beginPath();ctx.moveTo(cx-Math.cos(a)*span*.13,cy-Math.sin(a)*span*.13);ctx.lineTo(cx+Math.cos(a)*length,cy+Math.sin(a)*length);ctx.stroke()
                }
            }else if(root.particleState==="success"){
                const wave=span*(.24+.74*((time*.012)%1))
                ctx.strokeStyle="rgba(77,230,174,"+(1-wave/span)*.58+")";ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(cx,cy,wave,0,Math.PI*2);ctx.stroke()
            }else if(root.particleState==="error"){
                ctx.strokeStyle="rgba(255,91,74,.48)";ctx.lineWidth=1.1
                for(let arc=0;arc<4;++arc){const r=span*(.36+arc*.13),a=time*.004*(arc%2?1:-1)+arc;ctx.beginPath();ctx.arc(cx,cy,r,a,a+.36+root.instability*.22);ctx.stroke()}
            }else if(root.particleState==="listening"){
                for(let ray=0;ray<12;++ray){const a=ray*Math.PI/6+rotation*.2,r=span*(.72-.14*statePulse);ctx.strokeStyle="rgba(91,177,255,.18)";ctx.beginPath();ctx.moveTo(cx+Math.cos(a)*r,cy+Math.sin(a)*r);ctx.lineTo(cx+Math.cos(a)*span*.36,cy+Math.sin(a)*span*.36);ctx.stroke()}
            }

            // Sparse foreground motes travel faster and larger than the shell,
            // creating parallax without another renderer or dependency.
            if(root.qualityScale>.55){
                for(let i=0;i<46;++i){
                    const a=hash(i,53.2)*Math.PI*2+rotation*2.6
                    const r=span*(.56+hash(i,71.4)*.55)
                    const drift=Math.sin(time*.004+i)*span*.018*root.activity
                    dot(ctx,cx+Math.cos(a)*r+drift,cy+Math.sin(a)*r*.86,1.0+hash(i,42.1)*1.45,(.12+root.activity*.28)*(0.5+0.5*Math.sin(time*.003+i)),i%17===0)
                }
            }
        }

        function drawMission(ctx, cx, cy, halfWidth, halfHeight, count, time) {
            const wingCount = Math.floor(count / 2)
            for (let side = -1; side <= 1; side += 2) {
                for (let i = 0; i < wingCount; ++i) {
                    const u = hash(i, 4.7)
                    const v = hash(i, 9.1)
                    const bend = Math.sin((v - 0.5) * Math.PI) * halfWidth * 0.10
                    const inner = halfWidth * (0.27 + 0.10 * Math.abs(v - 0.5))
                    const spread = inner + Math.pow(u, 0.72) * halfWidth * 0.70
                    const x = cx + side * (spread + bend)
                    const y = cy + (v - 0.5) * halfHeight * 1.74 + Math.sin(time * 0.004 + i) * 1.6
                    const alpha = 0.18 + 0.76 * (1 - u) * (0.55 + 0.45 * hash(i, 2.3))
                    dot(ctx, x, y, 0.6 + 1.5 * (1 - u), alpha, i % 173 === 0)
                    if (i % 109 === 0)
                        dataSpark(ctx, x, y, 1.15, .64)
                    if (i % 31 === 0) {
                        ctx.strokeStyle = "rgba(33,119,244,0.18)"
                        ctx.beginPath(); ctx.moveTo(cx + side * inner, cy); ctx.quadraticCurveTo(x - side * 22, y, x, y); ctx.stroke()
                    }
                }
            }
            const bridge = ctx.createLinearGradient(cx - halfWidth * 0.32, cy, cx + halfWidth * 0.32, cy)
            bridge.addColorStop(0, "rgba(28,111,242,0)")
            bridge.addColorStop(0.5, "rgba(121,193,255,0.82)")
            bridge.addColorStop(1, "rgba(28,111,242,0)")
            ctx.strokeStyle = bridge; ctx.lineWidth = 1.2
            ctx.beginPath(); ctx.moveTo(cx - halfWidth * 0.32, cy); ctx.lineTo(cx + halfWidth * 0.32, cy); ctx.stroke()

            // Fine inward filaments make the parted wings read as the same
            // standby fabric opening a clean borderless answer aperture.
            for (let filament = 0; filament < 18; ++filament) {
                const y = cy + (filament - 8.5) * halfHeight * 0.085
                const inset = halfWidth * (0.24 + Math.abs(filament - 8.5) * 0.006)
                ctx.strokeStyle = filament % 6 === 0 ? "rgba(233,247,255,0.32)" : "rgba(43,128,255,0.14)"
                ctx.lineWidth = filament % 6 === 0 ? 0.85 : 0.5
                ctx.beginPath(); ctx.moveTo(cx - halfWidth * 0.94, y); ctx.quadraticCurveTo(cx - inset * 1.35, cy, cx - inset, y * 0.94 + cy * 0.06); ctx.stroke()
                ctx.beginPath(); ctx.moveTo(cx + halfWidth * 0.94, y); ctx.quadraticCurveTo(cx + inset * 1.35, cy, cx + inset, y * 0.94 + cy * 0.06); ctx.stroke()
            }
        }

        function drawGaming(ctx, cx, cy, span, count, time) {
            drawStandby(ctx, cx, cy, span, count, time)
            // Game mode injects disciplined acceleration lanes into the same
            // fabric; no separate overlay, logo, or fake loading spinner.
            for (let lane = 0; lane < 34; ++lane) {
                const angle = -1.15 + lane * .071 + Math.sin(time * .0012 + lane) * .022
                const inner = span * (.14 + (lane % 5) * .03)
                const outer = span * (.62 + (lane % 4) * .075)
                const glow = lane % 9 === 0
                ctx.strokeStyle = glow ? "rgba(255,164,60,.42)" : "rgba(54,150,255,.23)"
                ctx.lineWidth = glow ? 1.05 : .52
                ctx.beginPath()
                ctx.moveTo(cx + Math.cos(angle) * inner, cy + Math.sin(angle) * inner * .84)
                ctx.lineTo(cx + Math.cos(angle + .13) * outer, cy + Math.sin(angle + .13) * outer * .84)
                ctx.stroke()
            }
        }

        function drawFusionCore(ctx, cx, cy, radius, warm, time, direction) {
            const aura = ctx.createRadialGradient(cx, cy, radius * 0.05, cx, cy, radius * 1.08)
            aura.addColorStop(0, warm ? "rgba(255,210,155,0.42)" : "rgba(198,230,255,0.46)")
            aura.addColorStop(0.34, warm ? "rgba(255,137,25,0.20)" : "rgba(28,119,255,0.23)")
            aura.addColorStop(0.76, warm ? "rgba(170,73,8,0.07)" : "rgba(8,61,153,0.08)")
            aura.addColorStop(1, "rgba(0,0,0,0)")
            ctx.fillStyle = aura; ctx.beginPath(); ctx.arc(cx, cy, radius * 1.08, 0, Math.PI * 2); ctx.fill()
            for (let ring = 0; ring < 13; ++ring) {
                const r = radius * (0.16 + ring * 0.066)
                const start = time * 0.003 * direction + ring * 0.63
                ctx.strokeStyle = warm ? "rgba(255,151,45," + (0.18 + ring * 0.025) + ")"
                                       : "rgba(37,128,255," + (0.18 + ring * 0.025) + ")"
                ctx.lineWidth = ring % 2 ? 1.6 : 0.7
                for (let arc = 0; arc < 7; ++arc) {
                    const angle = start + arc * Math.PI * 0.285
                    ctx.beginPath(); ctx.arc(cx, cy, r, angle, angle + 0.29 + (ring % 3) * 0.07); ctx.stroke()
                }
            }
            for (let spoke = 0; spoke < 32; ++spoke) {
                const angle = spoke * Math.PI / 16 + time * .0007 * direction
                const inner = radius * (.22 + (spoke % 4) * .025)
                const outer = radius * (.68 + (spoke % 5) * .045)
                ctx.strokeStyle = warm ? "rgba(255,159,57,.19)" : "rgba(63,145,255,.20)"
                ctx.lineWidth = spoke % 4 === 0 ? 1.0 : .5
                ctx.beginPath(); ctx.moveTo(cx + Math.cos(angle) * inner, cy + Math.sin(angle) * inner)
                ctx.lineTo(cx + Math.cos(angle + .08 * direction) * outer, cy + Math.sin(angle + .08 * direction) * outer); ctx.stroke()
            }
            for (let i = 0; i < 840; ++i) {
                const angle = hash(i, 5.2) * Math.PI * 2 + time * 0.002 * direction
                const r = radius * (0.23 + 0.76 * Math.pow(hash(i, 8.9), 0.65))
                dot(ctx, cx + Math.cos(angle) * r, cy + Math.sin(angle) * r * 0.82,
                    0.65 + hash(i, 1.3) * 1.65, 0.30 + hash(i, 6.4) * 0.70, warm && i % 3 !== 0)
                if (i % 127 === 0)
                    dataSpark(ctx, cx + Math.cos(angle) * r, cy + Math.sin(angle) * r * .82, 1.25, .66)
                if (i % 37 === 0) {
                    ctx.strokeStyle = warm ? "rgba(255,157,54,0.16)" : "rgba(51,137,255,0.17)"
                    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(angle) * r, cy + Math.sin(angle) * r * 0.82); ctx.stroke()
                }
            }
            const glow = ctx.createRadialGradient(cx, cy, 2, cx, cy, radius * 0.24)
            glow.addColorStop(0, warm ? "rgba(255,244,222,0.94)" : "rgba(226,244,255,0.94)")
            glow.addColorStop(0.22, warm ? "rgba(255,148,38,0.50)" : "rgba(27,119,255,0.56)")
            glow.addColorStop(1, "rgba(0,0,0,0)")
            ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(cx, cy, radius * 0.24, 0, Math.PI * 2); ctx.fill()
        }

        function drawFusion(ctx, cx, cy, widthSpan, heightSpan, time) {
            const radius = Math.min(widthSpan * 0.31, heightSpan * 0.42)
            const left = cx - widthSpan * 0.27
            const right = cx + widthSpan * 0.27
            ctx.strokeStyle = "rgba(72,139,255,0.26)"; ctx.lineWidth = 1
            ctx.beginPath(); ctx.ellipse(left, cy + radius * 0.93, radius * 0.70, radius * 0.12, 0, 0, Math.PI * 2); ctx.stroke()
            ctx.strokeStyle = "rgba(255,155,48,0.24)"
            ctx.beginPath(); ctx.ellipse(right, cy + radius * 0.93, radius * 0.70, radius * 0.12, 0, 0, Math.PI * 2); ctx.stroke()
            drawFusionCore(ctx, left, cy, radius, false, time, 1)
            drawFusionCore(ctx, right, cy, radius, true, time, -1)
            for (let path = 0; path < 38; ++path) {
                const offset = (path - 18.5) / 18.5
                const control = offset * radius * 0.72
                ctx.strokeStyle = path % 7 === 0 ? "rgba(235,246,255,0.52)" : "rgba(45,126,255,0.20)"
                ctx.lineWidth = path % 7 === 0 ? 1.1 : 0.55
                ctx.beginPath(); ctx.moveTo(left + radius * 0.64, cy + control)
                ctx.bezierCurveTo(cx - radius * 0.18, cy - control, cx + radius * 0.18, cy + control, right - radius * 0.64, cy - control)
                ctx.stroke()
            }
            const bridgeGlow = ctx.createRadialGradient(cx, cy, 2, cx, cy, radius * 0.38)
            bridgeGlow.addColorStop(0, "rgba(239,248,255,0.92)")
            bridgeGlow.addColorStop(0.18, "rgba(43,131,255,0.48)")
            bridgeGlow.addColorStop(1, "rgba(0,0,0,0)")
            ctx.fillStyle = bridgeGlow; ctx.beginPath(); ctx.arc(cx, cy, radius * 0.38, 0, Math.PI * 2); ctx.fill()
            ctx.strokeStyle = "rgba(159,205,255,0.68)"; ctx.lineWidth = 1
            for (let edge = 0; edge < 6; ++edge) {
                const a = -Math.PI / 2 + edge * Math.PI / 3
                const next = -Math.PI / 2 + (edge + 1) * Math.PI / 3
                if (edge === 0) { ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * radius * .18, cy + Math.sin(a) * radius * .18) }
                ctx.lineTo(cx + Math.cos(next) * radius * .18, cy + Math.sin(next) * radius * .18)
            }
            ctx.stroke()
        }

        function drawAtlas(ctx, cx, cy, radius, count, time) {
            function pointInside(longitude, latitude, polygon) {
                let inside = false
                for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
                    const xi = polygon[i][0], yi = polygon[i][1]
                    const xj = polygon[j][0], yj = polygon[j][1]
                    const crosses = ((yi > latitude) !== (yj > latitude))
                        && (longitude < (xj - xi) * (latitude - yi) / ((yj - yi) || .00001) + xi)
                    if (crosses) inside = !inside
                }
                return inside
            }
            function isLand(longitude, latitude) {
                for (let i = 0; i < root.atlasContinents.length; ++i)
                    if (pointInside(longitude, latitude, root.atlasContinents[i])) return true
                return false
            }
            const targetLongitude = root.atlasLocationAvailable ? root.atlasLongitude * Math.PI / 180 : 0
            const rotation = time * 0.00055 - targetLongitude
            const atmosphere = ctx.createRadialGradient(cx - radius * .24, cy - radius * .22, radius * .08, cx, cy, radius * 1.04)
            atmosphere.addColorStop(0, "rgba(42,128,255,.10)")
            atmosphere.addColorStop(.60, "rgba(8,46,116,.055)")
            atmosphere.addColorStop(1, "rgba(0,0,0,0)")
            ctx.fillStyle = atmosphere; ctx.beginPath(); ctx.arc(cx, cy, radius * 1.04, 0, Math.PI * 2); ctx.fill()
            const meshNodes = []
            // Oversample candidates and retain every land point while only
            // keeping a sparse ocean shell. That makes continents legible at
            // dashboard distance rather than a few faint specks on an orb.
            const samples = count * 3
            for (let i = 0; i < samples; ++i) {
                const latitude = Math.asin(2 * hash(i, 8.2) - 1)
                const baseLongitude = hash(i, 3.6) * Math.PI * 2 - Math.PI
                const longitude = baseLongitude + rotation
                const land = isLand(baseLongitude * 180 / Math.PI, latitude * 180 / Math.PI)
                if (!land && i % 3 !== 0) continue
                const depth = Math.cos(latitude) * Math.sin(longitude)
                if (depth < -0.10) continue
                const x = cx + Math.cos(latitude) * Math.cos(longitude) * radius
                const y = cy - Math.sin(latitude) * radius
                dot(ctx, x, y, land ? 0.72 + hash(i, 4.4) * .74 : 0.34, land ? 0.72 + hash(i, 2.2) * .25 : 0.16, i % 257 === 0)
                if (land && i % 151 === 0)
                    dataSpark(ctx, x, y, 1.05, .62)
                if (land && i % 19 === 0)
                    meshNodes.push({ x: x, y: y, depth: depth })
            }
            // Sparse data routes over the land particle field give Atlas a
            // geographical neural mesh instead of a generic spinning orb.
            ctx.lineWidth = 0.48
            for (let i = 0; i < meshNodes.length; ++i) {
                const source = meshNodes[i]
                const target = meshNodes[(i * 7 + 19) % meshNodes.length]
                if (source.depth > 0.06 && target.depth > 0.06) {
                    ctx.strokeStyle = i % 11 === 0 ? "rgba(255,159,53,0.32)" : "rgba(58,148,255,0.20)"
                    ctx.beginPath(); ctx.moveTo(source.x, source.y); ctx.lineTo(target.x, target.y); ctx.stroke()
                }
            }
            ctx.strokeStyle = "rgba(53,137,255,0.26)"; ctx.lineWidth = 0.8
            ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2); ctx.stroke()
            for (let latitude = -2; latitude <= 2; ++latitude) {
                const fraction = latitude / 3.0
                const lineY = cy + fraction * radius
                const lineRadius = radius * Math.sqrt(1 - fraction * fraction)
                ctx.beginPath(); ctx.ellipse(cx, lineY, lineRadius, lineRadius * .12, 0, 0, Math.PI * 2); ctx.stroke()
            }
            for (let meridian = -2; meridian <= 2; ++meridian) {
                strokeTrajectory(ctx, cx, cy, radius * (.18 + Math.abs(meridian) * .11), radius, meridian * .12, 0, Math.PI * 2)
            }
            // A few partial orbital rails provide depth without turning the
            // Atlas view back into the old loop-de-loop effect.
            for (let rail = 0; rail < 4; ++rail) {
                const orbit = radius * (1.045 + rail * .042)
                const start = -.98 + rail * 1.47
                ctx.strokeStyle = rail === 2 ? "rgba(255,162,60,.38)" : "rgba(67,151,255,.26)"
                ctx.lineWidth = rail === 2 ? .9 : .55
                ctx.beginPath(); ctx.arc(cx, cy, orbit, start, start + .72); ctx.stroke()
            }
            if (root.atlasLocationAvailable) {
                const latitude = root.atlasLatitude * Math.PI / 180
                const longitude = targetLongitude + rotation
                const markerX = cx + Math.cos(latitude) * Math.cos(longitude) * radius
                const markerY = cy - Math.sin(latitude) * radius
                const glow = ctx.createRadialGradient(markerX, markerY, 1, markerX, markerY, 24)
                glow.addColorStop(0, "rgba(255,238,211,0.96)")
                glow.addColorStop(0.18, "rgba(255,157,50,0.80)")
                glow.addColorStop(1, "rgba(255,157,50,0)")
                ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(markerX, markerY, 24, 0, Math.PI * 2); ctx.fill()
                ctx.strokeStyle = "rgba(255,194,111,0.92)"; ctx.lineWidth = 1.2
                ctx.beginPath(); ctx.arc(markerX, markerY, 8, 0, Math.PI * 2); ctx.stroke()
                ctx.strokeStyle = "rgba(255,197,116,0.42)"; ctx.lineWidth = .7
                ctx.beginPath(); ctx.arc(markerX, markerY, 15, 0, Math.PI * 2); ctx.stroke()
                ctx.beginPath(); ctx.moveTo(markerX - 18, markerY); ctx.lineTo(markerX + 18, markerY); ctx.stroke()
                ctx.beginPath(); ctx.moveTo(markerX, markerY - 18); ctx.lineTo(markerX, markerY + 18); ctx.stroke()
            }
        }

        function drawMode(ctx, selectedMode, alpha, cx, cy, count, time) {
            ctx.save()
            ctx.globalAlpha = alpha
            if (selectedMode === "mission" || selectedMode === "answer")
                drawMission(ctx, cx, cy, width * 0.49, height * 0.49, count, time)
            else if (selectedMode === "fusion")
                drawFusion(ctx, cx, cy, width * 0.96, height * 0.92, time)
            else if (selectedMode === "atlas")
                drawAtlas(ctx, cx, cy, Math.min(width, height) * 0.39, count, time)
            else if (selectedMode === "gaming")
                drawGaming(ctx, cx, cy, Math.min(width, height) * 0.47, count, time)
            else
                drawStandby(ctx, cx, cy, Math.min(width, height) * 0.47 * (1 + root.expansion * .08), count, time)
            ctx.restore()
        }

        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            if (!root.active) return
            const cx = width * 0.5 + root.centerOffsetX
            const cy = height * 0.49
            const time = root.reducedMotion ? 0 : root.phase
            const requested = Math.max(320, Math.min(root.particleBudget * (.58 + root.density * .58), 3400))
            // Per-frame layers stay deliberately smaller than the cached
            // standby shell. Quality scales detail, while motion remains fluid.
            const count = root.renderedMode === "standby" ? Math.min(requested, 300)
                         : root.renderedMode === "atlas" ? Math.min(requested, Math.floor(1250 + 850 * root.qualityScale))
                         : root.renderedMode === "gaming" ? Math.min(requested, Math.floor(900 + 600 * root.qualityScale))
                         : Math.min(requested, Math.floor(700 + 350 * root.qualityScale))
            ctx.save()
            ctx.globalCompositeOperation = "lighter"
            if (root.transitionProgress < 1) {
                const transitionCount = Math.max(300, Math.floor(count * root.transitionDensity))
                drawMode(ctx, root.previousMode, 1 - root.transitionProgress, cx, cy, transitionCount, time)
                drawMode(ctx, root.renderedMode, root.transitionProgress, cx, cy, transitionCount, time)
            } else {
                drawMode(ctx, root.renderedMode, 1, cx, cy, count, time)
            }
            ctx.restore()
        }
    }

}
