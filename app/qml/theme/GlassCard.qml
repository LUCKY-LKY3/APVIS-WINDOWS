import QtQuick

// A dark glass card as in the owner's concept: an uppercase title, an optional
// count badge and chevron (the header opens the related page), and content.
// Rises in with the others when Home appears (`order` staggers it).
Item {
    id: card
    property string title: ""
    property string badge: ""
    property bool chevron: true
    property real padding: 18
    property real spacing: 10
    property int order: 0
    property bool shown: true
    property color tint: Theme.accent
    property bool live: false               // a gentle accent edge while something is happening
    default property alias content: column.data
    signal opened()
    implicitHeight: column.y + column.implicitHeight + padding
    height: implicitHeight

    opacity: 0
    transform: Translate { id: rise; y: 16 }
    states: State { name: "on"; when: card.shown
        PropertyChanges { target: card; opacity: 1 }
        PropertyChanges { target: rise; y: 0 } }
    transitions: [
        Transition { to: "on"
            SequentialAnimation {
                PauseAnimation { duration: 90 * card.order }
                ParallelAnimation {
                    NumberAnimation { target: card; property: "opacity"; duration: 480; easing.type: Easing.OutCubic }
                    NumberAnimation { target: rise; property: "y"; duration: 560; easing.type: Easing.OutCubic } } } },
        Transition { from: "on"
            ParallelAnimation {
                NumberAnimation { target: card; property: "opacity"; duration: 200 }
                NumberAnimation { target: rise; property: "y"; duration: 200 } } }
    ]

    Chamfer {
        anchors.fill: parent; cut: 12
        fill: Theme.panel; fillOpacity: 0.72; fill2: Theme.bgBottom; fill2Opacity: 0.78
        stroke: card.live ? Qt.rgba(card.tint.r, card.tint.g, card.tint.b, 0.55)
                          : headerMouse.containsMouse && card.chevron ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.45)
                                                                      : Qt.rgba(Theme.line.r, Theme.line.g, Theme.line.b, 0.95)
        edgeGlow: true; glowColour: card.live ? card.tint : Theme.accent
    }
    Item {
        id: header
        visible: card.title.length > 0
        x: card.padding; y: 0; width: parent.width - 2 * card.padding; height: 50
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: Theme.label(card.title)
            font.pixelSize: Theme.lacquer && !Theme.holo ? 14 : 12; font.letterSpacing: Theme.lacquer && !Theme.holo ? 0.2 : 2.0
            font.weight: Font.Medium; color: Theme.holo ? Qt.lighter(Theme.accent, 1.3) : Theme.text
        }
        Rectangle { visible: Theme.lacquer; y: 38; width: Theme.holo ? 34 : 22; height: Theme.holo ? 2 : 1.2; color: Theme.accent; opacity: 0.8 }
        Rectangle {
            visible: card.badge.length > 0
            anchors.right: chev.visible ? chev.left : parent.right; anchors.rightMargin: chev.visible ? 10 : 0
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(22, badgeText.implicitWidth + 12); height: 22; radius: 11
            color: Qt.rgba(card.tint.r, card.tint.g, card.tint.b, 0.2)
            border.width: 1; border.color: Qt.rgba(card.tint.r, card.tint.g, card.tint.b, 0.6)
            Text { id: badgeText; anchors.centerIn: parent; text: card.badge; color: Theme.text; font.pixelSize: 11 }
        }
        Text {
            id: chev
            visible: card.chevron
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            text: "›"; font.pixelSize: 20; color: headerMouse.containsMouse ? Theme.accent : Theme.muted
            Behavior on color { ColorAnimation { duration: 150 } }
        }
        MouseArea {
            id: headerMouse
            anchors.fill: parent; hoverEnabled: true
            enabled: card.chevron
            cursorShape: card.chevron ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: card.opened()
        }
    }
    Column {
        id: column
        x: card.padding; y: card.title.length > 0 ? 52 : card.padding
        width: parent.width - 2 * card.padding
        spacing: card.spacing
    }
}
