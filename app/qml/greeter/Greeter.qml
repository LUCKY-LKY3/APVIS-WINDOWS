import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "../theme"

// The APVIS login screen (V4): shown by greetd at every boot of an installed APVIS OS (apvis_os.greeter).
// Two accounts: APVIS (the owner, administrator) and Guest (look around, nothing is saved). Keyboard first:
// Tab, the arrows, Enter and Esc do everything; the mouse works too. The core is the Home core's art,
// still or drifting very slowly (a few textured layers at 15 fps; still on the CPU renderer).
Window {
    id: root
    visible: true
    visibility: previewWindowed ? Window.Windowed : Window.FullScreen
    flags: Qt.Window | Qt.FramelessWindowHint
    width: previewSize.width > 0 ? previewSize.width : 1920
    height: previewSize.height > 0 ? previewSize.height : 1080
    color: Theme.ink
    title: "APVIS OS"
    Binding { target: Theme; property: "accentName"; value: "lacquer" }

    // One unit scales the whole screen from the 1920x1080 design (the VM's 1024x768 included); text and the
    // boxes that hold it shrink less, so small screens stay readable.
    readonly property real u: Math.max(0.6, Math.min(height / 1080, width / 1366))
    readonly property real tu: Math.max(0.84, u)
    function px(v) { return Math.max(1, Math.round(v * u)) }
    function fpx(v) { return Math.max(1, Math.round(v * tu)) }
    readonly property string voice: Theme.voiceFont !== "" ? Theme.voiceFont : Qt.application.font.family

    readonly property var accounts: greeter.accounts || []
    readonly property int count: accounts.length
    property int selected: 0                     // the chosen account
    property int cursor: 0                       // keyboard position: accounts, then Restart, Shut down
    property string armed: ""                    // a power button waiting for its second press
    property bool leaving: false
    readonly property var account: accounts[selected] || ({})
    readonly property bool typing: field.activeFocus
    property date now: new Date()
    Timer { interval: 1000; running: true; repeat: true; onTriggered: root.now = new Date() }
    Timer { id: disarm; interval: 4000; onTriggered: root.armed = "" }

    function choose(i) { selected = i; cursor = i; armed = ""; greeter.clearMessage() }
    function move(step) {
        const n = count + 2
        cursor = (cursor + step + n) % n
        if (cursor < count) selected = cursor
        armed = ""
    }
    function openPassword(seed) {
        cursor = selected; armed = ""
        field.text = seed; field.forceActiveFocus(); field.cursorPosition = field.text.length
    }
    function closePassword() { field.text = ""; keys.forceActiveFocus() }
    function signIn() {
        if (greeter.busy || leaving) return
        if (account.password) { greeter.login(account.user, field.text); field.text = "" }
        else greeter.login(account.user, "")
    }
    function activate() {
        if (greeter.busy || leaving) return
        if (cursor < count) { if (accounts[cursor].password) openPassword(""); else signIn() }
        else pressPower(cursor === count ? "reboot" : "poweroff")
    }
    function pressPower(action) {
        if (armed === action) { armed = ""; greeter.power(action) }
        else { armed = action; disarm.restart() }
    }
    Component.onCompleted: {
        root.requestActivate()
        if (count && accounts[0].password) Qt.callLater(() => root.openPassword(""))
        else keys.forceActiveFocus()
    }
    Connections {
        target: greeter
        function onWrongPassword() { shake.restart(); root.openPassword("") }
        function onSignedIn() { root.leaving = true }
    }

    // Development renders (scripts/render-greeter.py): put the screen in a state without a person at it.
    Timer {
        running: previewState !== ""; interval: 300
        onTriggered: {
            if (previewState === "typing") root.openPassword("fakepw12")
            else if (previewState === "wrong") greeter.login("apvis", "not-the-password")
            else if (previewState === "busy") greeter.login("apvis", "slow-fake-password")
            else if (previewState === "guest") { root.closePassword(); root.choose(1) }
            else if (previewState === "power") { root.closePassword(); root.cursor = root.count; root.armed = "reboot" }
        }
    }

    // ---------------------------------------------------------------- keyboard
    Item {
        id: keys
        focus: true
        Keys.onPressed: event => {
            const k = event.key
            if (root.leaving) { event.accepted = true; return }
            if (k === Qt.Key_Tab) root.move(1)
            else if (k === Qt.Key_Backtab) root.move(-1)
            else if (k === Qt.Key_Left || k === Qt.Key_Up || k === Qt.Key_Right || k === Qt.Key_Down) {
                const step = (k === Qt.Key_Left || k === Qt.Key_Up) ? -1 : 1
                if (root.cursor < root.count) root.choose((root.selected + step + root.count) % root.count)
                else if (k === Qt.Key_Up) root.cursor = root.selected
                else root.cursor = root.cursor === root.count ? root.count + 1 : root.count
            }
            else if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) root.activate()
            else if (k === Qt.Key_Escape) {
                if (root.armed) root.armed = ""
                else if (root.cursor >= root.count) root.cursor = root.selected
                greeter.clearMessage()
            }
            else if (event.text.length === 1 && event.text > " " && root.cursor < root.count
                     && root.accounts[root.cursor].password && !greeter.busy) root.openPassword(event.text)
            else return
            event.accepted = true
        }
    }

    // ---------------------------------------------------------------- the room
    Image {
        anchors.fill: parent
        source: "../art/" + Theme.wallpaper
        fillMode: Image.PreserveAspectCrop
        opacity: 0.55
        asynchronous: true
    }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.shade(0.55) }
            GradientStop { position: 0.45; color: Theme.shade(0.2) }
            GradientStop { position: 1; color: Theme.shade(0.7) }
        }
    }

    Item {
        id: stage
        anchors.fill: parent
        opacity: root.leaving ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: 420; easing.type: Easing.InOutCubic } }
        property real rise: 0
        Component.onCompleted: rise = 1
        Behavior on rise { NumberAnimation { duration: 900; easing.type: Easing.OutCubic } }

        // ---- top: this computer, and the time
        Row {
            x: root.px(56); y: root.px(46)
            spacing: root.px(12)
            opacity: 0.9 * stage.rise
            ApvisMark { width: root.px(26); height: width; glow: 0.5; anchors.verticalCenter: parent.verticalCenter }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "APVIS OS"; color: Theme.muted
                font.pixelSize: root.fpx(13); font.letterSpacing: root.px(3); font.weight: Font.Medium
            }
        }
        Column {
            anchors.right: parent.right; anchors.rightMargin: root.px(60)
            y: root.px(34)
            opacity: stage.rise
            Text {
                anchors.right: parent.right
                text: Qt.formatDateTime(root.now, "HH:mm"); color: Theme.text
                font.pixelSize: root.px(52); font.weight: Font.Normal; font.letterSpacing: -root.px(1)
                opacity: 0.94
            }
            Text {
                anchors.right: parent.right
                text: Qt.formatDateTime(root.now, "dddd d MMMM"); color: Theme.muted
                font.pixelSize: root.fpx(16)
            }
        }

        // ---- the core with the wordmark
        Item {
            id: core
            width: root.px(560); height: width
            anchors.horizontalCenter: parent.horizontalCenter
            y: root.px(124) + (1 - stage.rise) * root.px(14)
            opacity: stage.rise
            readonly property real box: width * 0.9
            property real drift: 0
            // Very slow drift, 15 frames a second: next to nothing for the HD 4600; still on the CPU renderer.
            Timer { interval: 66; repeat: true; running: !greeter.software && !root.leaving
                    onTriggered: core.drift += 0.066 }
            component Layer: Image {
                property string art: ""
                anchors.centerIn: parent
                width: core.box; height: core.box
                source: "../art/" + art
                sourceSize: Qt.size(1024, 1024)
                smooth: true; mipmap: true
            }
            Layer { art: "hud-haze.png"; opacity: 0.55 }
            Layer { art: "hud-outer.png"; rotation: core.drift * 0.9 }
            Layer { art: "hud-ticks.png"; rotation: -core.drift * 0.35; opacity: 0.8 }
            Layer { art: "hud-segments.png"; rotation: 40 - core.drift * 1.4; opacity: 0.8 }
            Layer { art: "hud-bands.png"; rotation: 70 + core.drift * 2.2; opacity: 0.55 }
            Layer { art: "hud-dots.png"; rotation: core.drift * 0.6 }
            Layer { art: "hud-centre.png" }
            Layer { art: "hud-reactor.png"; opacity: 0.7 }
            Layer { art: "hud-inner.png"; rotation: 15 - core.drift * 1.8 }
            Column {
                anchors.centerIn: parent
                anchors.verticalCenterOffset: root.px(4)
                spacing: root.px(8)
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "APVIS"; color: Theme.text
                    font.family: root.voice; font.pixelSize: root.px(46)
                    font.letterSpacing: root.px(15); leftPadding: font.letterSpacing
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Welcome"; color: Theme.accent
                    font.family: root.voice; font.italic: true; font.pixelSize: root.px(18)
                    font.letterSpacing: root.px(1)
                }
            }
            Accessible.role: Accessible.Graphic
            Accessible.name: "APVIS"
        }

        // ---- the accounts
        Row {
            id: tiles
            anchors.horizontalCenter: parent.horizontalCenter
            y: core.y + core.height + root.px(10)
            spacing: root.px(24)
            opacity: stage.rise
            Repeater {
                model: root.accounts
                delegate: AbstractButton {
                    id: tile
                    required property var modelData
                    required property int index
                    readonly property bool chosen: root.selected === index
                    readonly property bool ringed: root.cursor === index && !root.typing && keys.activeFocus
                    width: root.fpx(340); height: root.px(98)
                    focusPolicy: Qt.NoFocus
                    Accessible.name: modelData.name + ", " + modelData.role
                    Accessible.role: Accessible.Button
                    onClicked: {
                        if (greeter.busy || root.leaving) return
                        if (tile.chosen && !tile.modelData.password) root.signIn()
                        else { root.choose(tile.index); if (tile.modelData.password) root.openPassword(""); else keys.forceActiveFocus() }
                    }
                    background: Item {
                        Chamfer {
                            anchors.fill: parent; cut: root.px(14)
                            opacity: tile.chosen ? 1 : 0.6
                            fill: tile.chosen ? Theme.raised : Theme.panel
                            fillOpacity: tile.chosen ? 0.92 : 0.55
                            fill2: Theme.bgBottom; fill2Opacity: tile.chosen ? 0.92 : 0.55
                            stroke: tile.chosen ? Theme.accent : Theme.line
                            edgeGlow: tile.chosen
                        }
                        Chamfer {                                  // keyboard focus ring
                            anchors.fill: parent; anchors.margins: -root.px(5); cut: root.px(17)
                            fill: Theme.ink; fillOpacity: 0; stroke: Theme.tint(Theme.text, 0.75); strokeWidth: 1.2
                            visible: tile.ringed
                        }
                    }
                    contentItem: Item {
                        opacity: tile.chosen ? 1 : 0.72
                        Behavior on opacity { NumberAnimation { duration: 180 } }
                        Item {                                     // the medallion
                            id: medal
                            x: root.px(22); anchors.verticalCenter: parent.verticalCenter
                            width: root.px(58); height: width
                            Rectangle {
                                anchors.fill: parent; radius: width / 2
                                color: Theme.tint(Theme.accent, tile.chosen ? 0.1 : 0.04)
                                border.width: 1
                                border.color: tile.chosen ? Theme.tint(Theme.accent, 0.75) : Theme.line
                            }
                            ApvisMark {
                                visible: tile.modelData.user === "apvis"
                                anchors.centerIn: parent; width: root.px(34); height: width
                                glow: tile.chosen ? 0.7 : 0.25
                                tint: tile.chosen ? Theme.accent : Theme.muted
                            }
                            Canvas {                               // a person, for Guest
                                id: person
                                visible: tile.modelData.user !== "apvis"
                                anchors.centerIn: parent; width: root.px(30); height: width
                                property color ink: tile.chosen ? Theme.text : Theme.muted
                                onInkChanged: requestPaint()
                                onWidthChanged: requestPaint()
                                onPaint: {
                                    const c = getContext("2d"), w = width, h = height
                                    c.reset(); c.strokeStyle = Theme.css(ink, 1); c.lineWidth = Math.max(1.2, w * 0.06); c.lineCap = "round"
                                    c.beginPath(); c.arc(w / 2, h * 0.33, w * 0.19, 0, Math.PI * 2); c.stroke()
                                    c.beginPath(); c.arc(w / 2, h * 1.02, w * 0.42, Math.PI * 1.13, Math.PI * 1.87); c.stroke()
                                }
                            }
                        }
                        Column {
                            anchors.left: medal.right; anchors.leftMargin: root.px(18)
                            anchors.right: parent.right; anchors.rightMargin: root.px(16)
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: root.px(5)
                            Text {
                                width: parent.width; elide: Text.ElideRight
                                text: tile.modelData.name; color: Theme.text
                                font.pixelSize: root.fpx(21); font.weight: Font.Medium
                            }
                            Text {
                                width: parent.width; elide: Text.ElideRight
                                text: tile.modelData.role
                                color: tile.chosen ? Theme.accent : Theme.muted
                                font.pixelSize: root.fpx(13)
                            }
                        }
                    }
                }
            }
        }

        // ---- the password (APVIS) or the way in (Guest)
        Item {
            id: entry
            anchors.horizontalCenter: parent.horizontalCenter
            y: tiles.y + tiles.height + root.px(30)
            width: root.fpx(420); height: root.px(52)
            opacity: stage.rise
            transform: Translate { id: shakeX }
            SequentialAnimation {
                id: shake
                NumberAnimation { target: shakeX; property: "x"; to: -root.px(10); duration: 50 }
                NumberAnimation { target: shakeX; property: "x"; to: root.px(10); duration: 70 }
                NumberAnimation { target: shakeX; property: "x"; to: -root.px(6); duration: 60 }
                NumberAnimation { target: shakeX; property: "x"; to: 0; duration: 60 }
            }
            Item {
                anchors.fill: parent
                visible: !!root.account.password
                Chamfer {
                    anchors.fill: parent; cut: root.px(12)
                    fill: Theme.panel; fillOpacity: 0.9; fill2: Theme.bgBottom; fill2Opacity: 0.9
                    stroke: field.activeFocus ? Theme.accent : Theme.line
                }
                Glyph {
                    x: root.px(18); anchors.verticalCenter: parent.verticalCenter
                    width: root.px(16); height: width; kind: "key"
                    stroke: field.activeFocus ? Theme.accent : Theme.muted
                }
                TextField {
                    id: field
                    x: root.px(46); width: parent.width - x - root.px(58); height: parent.height
                    echoMode: TextInput.Password; passwordCharacter: "•"
                    placeholderText: greeter.busy ? "Checking…" : "Password"
                    color: Theme.text; placeholderTextColor: Theme.muted
                    selectionColor: Theme.accentSoft; selectedTextColor: Theme.text
                    font.pixelSize: root.fpx(17); font.letterSpacing: field.text.length ? root.px(2) : 0
                    verticalAlignment: TextInput.AlignVCenter
                    leftPadding: 0; rightPadding: 0
                    readOnly: greeter.busy
                    background: Item {}
                    Accessible.name: "Password for " + (root.account.name || "")
                    onAccepted: root.signIn()
                    onTextChanged: if (text.length) greeter.clearMessage()
                    Keys.onEscapePressed: root.closePassword()
                    Keys.onTabPressed: { root.closePassword(); root.move(1) }
                    Keys.onBacktabPressed: { root.closePassword(); root.move(-1) }
                    Keys.onUpPressed: { root.closePassword(); root.choose((root.selected + root.count - 1) % root.count) }
                    Keys.onDownPressed: { root.closePassword(); root.choose((root.selected + 1) % root.count) }
                }
                AbstractButton {
                    id: go
                    anchors.right: parent.right; anchors.rightMargin: root.px(8); anchors.verticalCenter: parent.verticalCenter
                    width: root.px(40); height: width
                    focusPolicy: Qt.NoFocus
                    Accessible.name: "Sign in"
                    onClicked: root.signIn()
                    background: Chamfer {
                        cut: root.px(8)
                        fill: field.text.length ? Theme.accent : Theme.raised
                        fillOpacity: field.text.length ? 0.95 : 0.6
                        stroke: field.text.length ? Theme.accent : Theme.line
                    }
                    contentItem: Text {
                        text: "→"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        color: field.text.length ? Theme.accentInk : Theme.muted; font.pixelSize: root.fpx(18)
                    }
                }
            }
            AbstractButton {
                id: lookAround
                anchors.fill: parent
                visible: !root.account.password
                focusPolicy: Qt.NoFocus
                Accessible.name: "Look around as Guest"
                onClicked: root.signIn()
                background: Chamfer {
                    cut: root.px(12)
                    fill: Theme.accent; fillOpacity: lookAround.hovered ? 1 : 0.92
                    stroke: Theme.accent
                }
                contentItem: Text {
                    text: greeter.busy ? "Opening…" : "Look around  →"
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    color: Theme.accentInk; font.pixelSize: root.fpx(16); font.weight: Font.DemiBold
                    font.letterSpacing: root.px(0.5)
                }
            }
            Rectangle {                                    // working: a thin line runs under the field
                visible: greeter.busy
                anchors.top: parent.bottom; anchors.topMargin: root.px(6)
                width: parent.width; height: 2; color: Theme.tint(Theme.accent, 0.12)
                clip: true
                Rectangle {
                    width: parent.width * 0.28; height: parent.height; color: Theme.accent
                    SequentialAnimation on x {
                        running: greeter.busy; loops: Animation.Infinite
                        NumberAnimation { from: -entry.width * 0.28; to: entry.width; duration: 1100; easing.type: Easing.InOutSine }
                    }
                }
            }
        }

        Text {
            id: note
            anchors.horizontalCenter: parent.horizontalCenter
            y: entry.y + entry.height + root.px(22)
            width: root.fpx(560)
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
            text: greeter.message
            color: greeter.tone === "error" ? Theme.attention : Theme.muted
            font.pixelSize: root.fpx(14)
            opacity: text.length ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 200 } }
        }

        // ---- bottom: the keys, and power
        Row {
            x: root.px(56); anchors.bottom: parent.bottom; anchors.bottomMargin: root.px(44)
            spacing: root.px(26)
            opacity: 0.85 * stage.rise
            Repeater {
                model: [["Tab", "Choose"], ["Enter", "Sign in"], ["Esc", "Back"]]
                delegate: Row {
                    required property var modelData
                    spacing: root.px(8)
                    Item {
                        width: Math.max(root.fpx(30), cap.implicitWidth + root.fpx(14)); height: root.fpx(22)
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle { anchors.fill: parent; radius: root.px(4); color: Theme.tint(Theme.text, 0.04); border.width: 1; border.color: Theme.line }
                        Text { id: cap; anchors.centerIn: parent; text: modelData[0]; color: Theme.text; font.pixelSize: root.fpx(11); font.weight: Font.Medium }
                    }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: modelData[1]; color: Theme.muted; font.pixelSize: root.fpx(12) }
                }
            }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: root.px(52)
            anchors.bottom: parent.bottom; anchors.bottomMargin: root.px(32)
            spacing: root.px(14)
            opacity: stage.rise
            Repeater {
                model: [["reboot", "Restart", "restart"], ["poweroff", "Shut down", "power"]]
                delegate: AbstractButton {
                    id: pb
                    required property var modelData
                    required property int index
                    readonly property bool isArmed: root.armed === modelData[0]
                    readonly property bool ringed: root.cursor === root.count + index && keys.activeFocus
                    width: root.fpx(104); height: root.px(70)
                    focusPolicy: Qt.NoFocus
                    Accessible.name: isArmed ? "Confirm " + modelData[1] : modelData[1]
                    onClicked: { root.cursor = root.count + index; root.pressPower(modelData[0]) }
                    background: Item {
                        Chamfer {
                            anchors.fill: parent; cut: root.px(9)
                            visible: pb.isArmed || pb.hovered || pb.ringed
                            fill: pb.isArmed ? Theme.attention : Theme.panel
                            fillOpacity: pb.isArmed ? 0.12 : 0.7
                            stroke: pb.ringed ? Theme.text : pb.isArmed ? Theme.attention : Theme.line
                            strokeWidth: pb.ringed ? 1.5 : 1
                        }
                    }
                    contentItem: Column {
                        spacing: root.px(8)
                        topPadding: root.px(12)
                        Glyph {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: root.px(20); height: width; kind: pb.modelData[2]
                            stroke: pb.isArmed ? Theme.attention : (pb.hovered || pb.ringed) ? Theme.accent : Theme.text
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: pb.isArmed ? "Press again" : pb.modelData[1]
                            color: pb.isArmed ? Theme.attention : Theme.muted; font.pixelSize: root.fpx(12)
                        }
                    }
                }
            }
        }
    }
}
