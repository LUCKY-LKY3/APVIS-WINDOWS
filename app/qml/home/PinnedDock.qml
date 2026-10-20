import QtQuick
import QtQuick.Controls
import "../theme"

// Pinned apps (pinned from the Apps Store): a small dock under the action tiles.
// Only what the owner pinned, resolved against this computer's real apps.
Item {
    id: dock
    signal act(string key)
    readonly property var st: shell.apps || ({})
    readonly property var items: {
        const out = [], inst = {}, cat = {}, bi = {}
        for (const a of (st.installed || [])) inst[a.id] = a
        for (const c of (st.catalog || [])) cat[c.id] = c
        for (const b of (st.builtin || [])) bi[b.id] = b
        for (const key of ((st.prefs || {}).pinned || [])) {
            const id = key.slice(2)
            if (key.startsWith("i:") && inst[id]) out.push({ key: key, name: inst[id].name, icon: inst[id].icon, launch: id })
            else if (key.startsWith("c:") && cat[id] && cat[id].openable)
                out.push({ key: key, name: cat[id].name, icon: inst[cat[id].desktop] ? inst[cat[id].desktop].icon : "", launch: cat[id].desktop })
            else if (key.startsWith("b:") && bi[id]) out.push({ key: key, name: bi[id].name, glyph: bi[id].glyph, action: bi[id].action })
        }
        return out
    }
    visible: items.length > 0
    implicitWidth: row.width + 24
    implicitHeight: 64

    Chamfer { anchors.fill: parent; cut: 10; fill: Theme.panel; fillOpacity: 0.55; stroke: Theme.line }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 10
        Repeater {
            model: dock.items
            delegate: AbstractButton {
                id: pin
                required property var modelData
                width: 46; height: 46
                hoverEnabled: true
                Accessible.name: "Open " + modelData.name
                ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: modelData.name
                onClicked: {
                    shell.noteApp(modelData.key)
                    if (modelData.action) dock.act(modelData.action)
                    else shell.launchApp(modelData.launch)
                }
                background: Rectangle { radius: 12; color: pin.hovered ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.14) : "transparent"
                                        border.width: pin.hovered ? 1 : 0; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.5)
                                        Behavior on color { ColorAnimation { duration: 150 } } }
                contentItem: Item {
                    Image {
                        id: img
                        anchors.centerIn: parent; width: 32; height: 32
                        visible: status === Image.Ready && implicitWidth > 1
                        source: pin.modelData.icon ? "image://appicon/" + encodeURIComponent(pin.modelData.icon) : ""
                        sourceSize: Qt.size(64, 64); asynchronous: true; smooth: true
                    }
                    Glyph { visible: !img.visible && !!pin.modelData.glyph; anchors.centerIn: parent; width: 26; height: 26
                            kind: pin.modelData.glyph || "apps"; stroke: Theme.accent }
                    Text { visible: !img.visible && !pin.modelData.glyph; anchors.centerIn: parent
                           text: pin.modelData.name.charAt(0).toUpperCase(); color: Theme.accent; font.pixelSize: 20; font.weight: Font.DemiBold }
                }
            }
        }
    }
}
