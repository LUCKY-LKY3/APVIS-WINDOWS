import QtQuick
import QtQuick.Controls
import "../theme"

// Install APVIS OS onto a whole disk (live USB only). Four steps: choose the
// disk, see what happens to Ollama, set the password, type the disk's name to
// confirm. Progress and the final result come from the installer itself.
Item {
    id: page
    readonly property var inst: shell.installer || ({})
    property var chosen: null
    readonly property var ollama: inst.ollama || ({})
    readonly property bool hasOllama: !!ollama.models_dir
    property bool keepModels: true
    property bool setupAi: true
    readonly property bool installing: inst.state === "installing"
    readonly property bool finished: inst.state === "done"
    function gb(n) { return (n / 1073741824).toFixed(n > 100 * 1073741824 ? 0 : 1) + " GB" }
    onVisibleChanged: if (visible && ["idle", "error"].indexOf(inst.state) >= 0 && !chosen) shell.installerDisks()
    Component.onCompleted: if (visible) shell.installerDisks()

    PageHeader {
        id: header
        width: parent.width
        code: "00"; title: "INSTALL APVIS OS"
        subtitle: "Puts APVIS OS on this computer's disk so it starts without the USB and keeps your settings, memory and updates. " +
                  "The disk you choose is erased completely."
    }

    component Step: Item {
        id: step
        property int n: 1
        property string title: ""
        property bool active: true
        property bool complete: false
        default property alias content: body.data
        width: parent ? parent.width : 400
        height: body.height + 58
        opacity: active || complete ? 1 : 0.4
        Behavior on opacity { NumberAnimation { duration: 200 } }
        Chamfer { anchors.fill: parent; cut: 12; fill: Theme.raised; fillOpacity: 0.8; fill2: Theme.bgBottom; fill2Opacity: 0.75
                  stroke: step.complete ? Theme.accent : Theme.line; edgeGlow: step.active; brackets: step.active }
        Rectangle { x: 14; y: 12; width: 22; height: 22; radius: 11; color: step.complete ? Theme.accent : "transparent"
                    border.width: 1.5; border.color: step.complete || step.active ? Theme.accent : Theme.muted
                    Text { anchors.centerIn: parent; text: step.complete ? "✓" : step.n; font.pixelSize: 11
                           color: step.complete ? Theme.bgBottom : Theme.text } }
        Text { x: 46; y: 15; text: step.title; color: Theme.text; font.family: Theme.monoFont; font.pixelSize: 11; font.letterSpacing: Theme.caps ? 2 : 0.3; font.bold: true }
        Column { id: body; x: 46; y: 44; width: parent.width - 60; spacing: 8; enabled: step.active }
    }

    // Once installing starts (or ends), bring the progress panel into view.
    // (after the panel has grown, so wait a moment and follow later changes too).
    onInstChanged: if (installing || finished || inst.state === "error") followProgress.restart()
    Timer { id: followProgress; interval: 250; onTriggered: flick.contentY = Math.max(0, flick.contentHeight - flick.height) }
    Flickable {
        id: flick
        anchors.fill: parent; anchors.topMargin: header.height + 14
        Behavior on contentY { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
        contentHeight: col.height + 20; clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: HudScrollBar {}
        Column {
            id: col
            width: Math.min(parent.width - 14, 900); spacing: 12

            Step {
                n: 1; title: "CHOOSE THE DISK"
                active: !page.installing && !page.finished
                complete: !!page.chosen
                Text { visible: page.inst.state === "scanning"; text: page.inst.message || ""; color: Theme.muted; font.pixelSize: 12 }
                Repeater {
                    model: page.inst.disks || []
                    delegate: HudButton {
                        required property var modelData
                        width: parent.width; implicitHeight: 52
                        tone: page.chosen && page.chosen.path === modelData.path ? "selected" : "normal"
                        caption: modelData.model + "  ·  " + page.gb(modelData.size) + "  ·  " + modelData.name +
                                 (modelData.partitions.length ? "  ·  has " + modelData.partitions.length + " partitions (will be erased)" : "  ·  empty")
                        onClicked: { page.chosen = modelData; confirmField.text = ""; shell.installerScan(modelData.path) }
                    }
                }
                Text { visible: page.inst.state === "choose" && (page.inst.disks || []).length === 0
                       text: page.inst.message || ""; color: Theme.attention; font.pixelSize: 12 }
                Text { text: "Only this computer's internal disks are listed. The USB stick APVIS is running from is never offered."
                       color: Theme.muted; font.pixelSize: 11; width: parent.width; wrapMode: Text.WordWrap }
            }

            Step {
                n: 2; title: "YOUR AI MODELS"
                active: !!page.chosen && !page.installing && !page.finished
                complete: !!page.chosen && !page.ollama.scanning && (page.ollama.none || page.hasOllama)
                Text {
                    width: parent.width; wrapMode: Text.WordWrap; font.pixelSize: 13
                    color: page.hasOllama && page.ollama.fits === false ? Theme.attention : Theme.text
                    text: !page.chosen ? "Choose a disk first." :
                          page.ollama.scanning ? "Looking for Ollama on " + page.chosen.name + "…" :
                          page.hasOllama ? ("Found Ollama with " + page.ollama.models.length + " models (" + page.gb(page.ollama.total_bytes) + "): " +
                                            page.ollama.models.join(", ") + ". " +
                                            (page.ollama.fits ? "They'll be copied to memory before the disk is erased and put back afterwards, so Ask works straight away."
                                                              : "They don't fit in this computer's free memory for the backup, so they can't be kept.")) :
                          "No Ollama install found on this disk. You can add models later with Ollama."
                }
                HudButton {
                    visible: page.hasOllama && page.ollama.fits
                    width: 260; caption: page.keepModels ? "Keeping my models ✓" : "Don't keep my models"
                    tone: page.keepModels ? "selected" : "normal"
                    onClicked: page.keepModels = !page.keepModels
                }
                HudToggle {
                    visible: !!page.chosen && !(page.hasOllama && page.ollama.fits && page.keepModels)
                    width: parent.width; on: page.setupAi
                    caption: "Set up local AI on the first start"
                    detail: "Installs Ollama and the recommended models (llama3.2:1b, qwen2.5-coder:1.5b and qwen2.5:0.5b, about 2.7 GB) when APVIS first starts online. Progress shows on Home."
                    onClicked: page.setupAi = !page.setupAi
                }
            }

            Step {
                n: 3; title: "YOUR PASSWORD"
                active: !!page.chosen && !page.installing && !page.finished
                complete: pw1.text.length >= 6 && pw1.text === pw2.text
                Text { width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 12
                       text: "APVIS starts straight to Home. This password is for admin tasks (sudo) and a future lock screen. At least 6 characters." }
                Row {
                    spacing: 8
                    component Pw: TextField {
                        width: 220; height: 38; echoMode: TextInput.Password; verticalAlignment: TextInput.AlignVCenter
                        color: Theme.text; placeholderTextColor: Theme.muted; font.pixelSize: 13
                        background: Rectangle { radius: 6; color: Theme.raised; border.width: parent.activeFocus ? 2 : 1
                                                border.color: parent.activeFocus ? Theme.accent : Theme.line }
                    }
                    Pw { id: pw1; placeholderText: "Password"; Accessible.name: "Password" }
                    Pw { id: pw2; placeholderText: "Type it again"; Accessible.name: "Password again" }
                }
                Text { visible: pw2.text.length > 0 && pw1.text !== pw2.text; text: "The two passwords don't match."
                       color: Theme.attention; font.pixelSize: 12 }
            }

            Step {
                id: confirmStep
                n: 4; title: "CONFIRM"
                readonly property bool ready: !!page.chosen && pw1.text.length >= 6 && pw1.text === pw2.text && !page.ollama.scanning
                active: ready && !page.installing && !page.finished
                complete: page.installing || page.finished
                Text { width: parent.width; wrapMode: Text.WordWrap; color: Theme.attention; font.pixelSize: 13
                       text: page.chosen ? "Everything on " + page.chosen.model + " (" + page.gb(page.chosen.size) + ", " + page.chosen.name +
                                           ") will be erased, including any other operating system on it. Type " + page.chosen.name + " to confirm."
                                         : "Choose a disk first." }
                Row {
                    spacing: 8
                    TextField {
                        id: confirmField
                        width: 220; height: 40; verticalAlignment: TextInput.AlignVCenter
                        placeholderText: page.chosen ? "Type " + page.chosen.name : ""
                        color: Theme.text; placeholderTextColor: Theme.muted; font.family: Theme.monoFont; font.pixelSize: 14
                        Accessible.name: "Type the disk name to confirm"
                        background: Rectangle { radius: 6; color: Theme.raised; border.width: confirmField.activeFocus ? 2 : 1
                                                border.color: confirmField.activeFocus ? Theme.attention : Theme.line }
                    }
                    HudButton {
                        width: 220; glyph: "check"; tone: "warning"
                        enabled: !!page.chosen && confirmField.text === page.chosen.name && confirmStep.ready
                        caption: "Erase and install"
                        onClicked: shell.installerStart(page.chosen.path, pw1.text,
                                                        page.hasOllama && page.ollama.fits && page.keepModels,
                                                        page.setupAi && !(page.hasOllama && page.ollama.fits && page.keepModels))
                    }
                }
            }

            // Progress / result.
            Item {
                visible: page.installing || page.finished || page.inst.state === "error"
                width: parent.width; height: progCol.height + 32
                Chamfer { anchors.fill: parent; cut: 12; fill: Theme.panel; fillOpacity: 0.9
                          stroke: page.inst.state === "error" ? Theme.attention : Theme.accent }
                Column {
                    id: progCol
                    x: 16; y: 16; width: parent.width - 32; spacing: 10
                    Text { text: page.finished ? Theme.label("INSTALLED") : page.inst.state === "error" ? Theme.label("INSTALL STOPPED") : "INSTALLING…"
                           color: page.inst.state === "error" ? Theme.attention : Theme.accent
                           font.family: Theme.monoFont; font.pixelSize: 12; font.letterSpacing: Theme.caps ? 2 : 0.3; font.bold: true }
                    Item {
                        width: parent.width; height: 8
                        Rectangle { anchors.fill: parent; radius: 4; color: Theme.raised }
                        Rectangle { height: parent.height; radius: 4; color: page.inst.state === "error" ? Theme.attention : Theme.accent
                                    width: parent.width * Math.max(0, Math.min(100, page.inst.pct || 0)) / 100
                                    Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } } }
                    }
                    Text { width: parent.width; wrapMode: Text.WordWrap; text: page.inst.message || ""; font.pixelSize: 13
                           color: page.inst.state === "error" ? Theme.attention : Theme.text }
                    Text { visible: page.installing; text: "Keep the USB stick in and don't turn the computer off."; color: Theme.muted; font.pixelSize: 11 }
                    HudButton { visible: page.finished; width: 220; glyph: "restart"; tone: "primary"
                                caption: "Restart now"; onClicked: shell.restartComputer() }
                    HudButton { visible: page.inst.state === "error"; width: 160; caption: "Try again"
                                onClicked: { page.chosen = null; shell.installerDisks() } }
                }
            }
        }
    }
}
