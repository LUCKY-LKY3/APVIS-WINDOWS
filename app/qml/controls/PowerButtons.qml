import QtQuick
import "../theme"

// Sleep / Restart / Shut down / Log out. The first press arms a button (amber,
// "Press again"), a second press within 4 s confirms. Used by Settings, the
// Control Centre and the top-bar power menu, so they always behave the same.
Row {
    id: power
    property real buttonWidth: 110
    property string armed: ""
    signal chosen(string action)
    spacing: 6
    Timer { id: disarm; interval: 4000; onTriggered: power.armed = "" }
    Repeater {
        // Guest (V4 login screen) may only log out; restart and shut down are on the login screen.
        model: shell.guest ? [["logout", "Log out", "logout"]]
                           : [["suspend", "Sleep", "moon"], ["reboot", "Restart", "restart"],
                              ["poweroff", "Shut down", "power"], ["logout", "Log out", "logout"]]
        delegate: HudButton {
            required property var modelData
            width: power.buttonWidth
            glyph: modelData[2]
            tone: power.armed === modelData[0] ? "warning" : "normal"
            caption: power.armed === modelData[0] ? "Press again" : modelData[1]
            Accessible.name: power.armed === modelData[0] ? "Confirm " + modelData[1] : modelData[1]
            onClicked: {
                if (power.armed === modelData[0]) {
                    power.armed = ""
                    shell.requestPower(modelData[0])      // Home shows the goodbye screen, then acts
                    power.chosen(modelData[0])
                } else {
                    power.armed = modelData[0]
                    disarm.restart()
                }
            }
        }
    }
}
