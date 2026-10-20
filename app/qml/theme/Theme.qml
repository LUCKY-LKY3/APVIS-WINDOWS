pragma Singleton
import QtQuick

// APVIS V2 colour tokens. Behaviour never depends on colour; the owner picks
// the accent from real renders (owner chose emerald-silver on 2026-09-23).
QtObject {
    id: theme
    property string accentName: "apvis"
    // A folder (file URL, ending in "/") with other core and nebula art; only design previews set it.
    property string artDir: ""
    // Panel style: "glass" (rounded, the owner's concept, 2026-09-26) or "hud" (chamfered).
    property string style: "glass"
    readonly property bool glass: style !== "hud"

    readonly property var accents: ({
        // The owner's concept (2026-09-26): pure black, neon green, dark glass.
        "apvis":      { accent: "#4cc983", accentSoft: "#2b7a50", line: "#223329", panel: "#040907", raised: "#08110c", hover: "#10201a",
                        bgTop: "#030805", bgMid: "#010402", bgBottom: "#000000", text: "#e9f0eb", muted: "#86a092", glow: "#1f6b40" },
        "emerald":    { accent: "#62e3b1", accentSoft: "#2a8a67", line: "#315a4b", panel: "#091510", raised: "#10241d", hover: "#18392c",
                        bgTop: "#0b1913", bgMid: "#07100c", bgBottom: "#030806", text: "#e4f2eb", muted: "#91ada0", glow: "#23684c" },
        "cyan-steel": { accent: "#6cc6ff", accentSoft: "#2e6f96", line: "#2c4b5e", panel: "#08121a", raised: "#0e1f2b", hover: "#16324a",
                        bgTop: "#0a141c", bgMid: "#060d13", bgBottom: "#03070a", text: "#e3eef5", muted: "#8fa6b3", glow: "#1f5577" },
        // Owner-requested blends of emerald and cyan-steel (2026-09-23).
        "aqua":       { accent: "#64d6d6", accentSoft: "#2c7d80", line: "#2e5357", panel: "#081415", raised: "#0f2225", hover: "#17363a",
                        bgTop: "#0a1718", bgMid: "#060f10", bgBottom: "#030708", text: "#e3f0f0", muted: "#90aaaa", glow: "#215f62" },
        "emerald-steel": { accent: "#62e3b1", accentSoft: "#2a8a67", line: "#2c4b5e", panel: "#08121a", raised: "#0e1f2b", hover: "#16324a",
                        bgTop: "#0a141c", bgMid: "#060d13", bgBottom: "#03070a", text: "#e3eef5", muted: "#8fa6b3", glow: "#23684c" },
        "emerald-silver": { accent: "#62e3b1", accentSoft: "#2a8a67", line: "#454d51", panel: "#0d1012", raised: "#161a1d", hover: "#23292d",
                        bgTop: "#121518", bgMid: "#0a0c0e", bgBottom: "#050607", text: "#eef2f4", muted: "#9aa3a8", glow: "#23684c" },
        "cool-white": { accent: "#dfe8ee", accentSoft: "#7d8a93", line: "#3a4248", panel: "#0d1012", raised: "#161a1d", hover: "#23292d",
                        bgTop: "#121518", bgMid: "#0a0c0e", bgBottom: "#050607", text: "#eef2f4", muted: "#9aa3a8", glow: "#4a555c" },
        // V3: lacquer and brass (the owner's pick, 2026-10-06): APVIS's look from V3 on, with the brass
        // instrument core. "v3b" (black and bright gold) stays a development preview only.
        "lacquer": { accent: "#b8893b", accentSoft: "#6e5228", line: "#2e271d", panel: "#14110d", raised: "#1c1812", hover: "#262017",
                bgTop: "#14100b", bgMid: "#0e0b08", bgBottom: "#0b0907", text: "#f2ebdd", muted: "#9c9180", glow: "#5c431c",
                attention: "#8fb4d9", warm: "#d8a35a", info: "#9fb7cf", signal: "#8fb4d9",
                ink: "#0b0907", accentInk: "#14110d", terminal: "#0d0a07",
                coreTint: "#e3c58a", coreHighlight: "#f2ebdd", markGlint: "#f6e7c4",
                atlasFloorTop: "#120e0a", atlasFloorMid: "#0d0a07", atlasFloorBottom: "#0b0907", atlasGrid: "#b8893b", atlasBadgeText: "#14110d",
                seaShallow: "#1d2a2e", seaMid: "#121b1e", seaDeep: "#090e10", bandHigh: "#e3c58a",
                marketTop: "#17120c", marketBase: "#0b0907", marketLine: "#2e271d", marketBadge: "#241c11", marketFade: "#100c08",
                marketPanel: "#15100b", marketText: "#efe3cc", marketMuted: "#9c9180", marketUpTop: "#13140b", marketDownTop: "#1a0d0b",
                marketMid: "#0e0b08", marketValue: "#f2ebdd",
                monoFont: "Inter", voiceFont: "EB Garamond 12", bodyFont: "Inter", caps: true, hudGrid: true,
                coreStyle: "hud", wallpaper: "lacquer.png", markGlow: 0.55, panelStyle: "holo" },
        // APVIS 7 "Neural Fabric" (owner, 2026-10-20: "go back to our apvis ways ... the blue image"): near-black and
        // cobalt with the V7 particle-field core. The default for APVIS for Windows.
        "neural": { accent: "#2e91ff", accentSoft: "#164a8f", line: "#13243b", panel: "#030a16", raised: "#071224", hover: "#0d1d36",
                bgTop: "#00040b", bgMid: "#000209", bgBottom: "#000103", text: "#d8e5f6", muted: "#62748a", glow: "#0d3a7a",
                attention: "#ff9d32", warm: "#ffb35c", info: "#7fb4ff", signal: "#35e69a",
                ink: "#000103", accentInk: "#000103", terminal: "#010610",
                coreTint: "#197cff", coreHighlight: "#dbeaff", markGlint: "#dbeaff",
                atlasFloorTop: "#010712", atlasFloorMid: "#00040b", atlasFloorBottom: "#000103", atlasGrid: "#126eff", atlasBadgeText: "#000103",
                seaShallow: "#06203f", seaMid: "#03142b", seaDeep: "#010a18", bandHigh: "#7fb4ff",
                marketTop: "#020b18", marketBase: "#000103", marketLine: "#13243b", marketBadge: "#0a1a33", marketFade: "#010610",
                marketPanel: "#030a16", marketText: "#d8e5f6", marketMuted: "#62748a", marketUpTop: "#03140f", marketDownTop: "#1a0b05",
                marketMid: "#00040b", marketValue: "#dbeaff",
                monoFont: "Inter", voiceFont: "", bodyFont: "Inter", caps: true, hudGrid: true,
                coreStyle: "jarvis", wallpaper: "neural.png", markGlow: 0.7, panelStyle: "holo" },
        "v3b": { accent: "#e8b33a", accentSoft: "#7a5314", line: "#2a2824", panel: "#0b0b0b", raised: "#141414", hover: "#1f1e1c",
                bgTop: "#0b0b0b", bgMid: "#050505", bgBottom: "#000000", text: "#f7f5f0", muted: "#a5a29b", glow: "#7a5314",
                attention: "#8fb4d9", warm: "#ffcf5c", info: "#9fc2e6", signal: "#8fb4d9",
                ink: "#000000", accentInk: "#000000", terminal: "#050505",
                coreTint: "#ffd36b", coreHighlight: "#fff6dc", markGlint: "#fff1c9",
                atlasFloorTop: "#0a0a0a", atlasFloorMid: "#050505", atlasFloorBottom: "#000000", atlasGrid: "#e8b33a", atlasBadgeText: "#000000",
                seaShallow: "#16222a", seaMid: "#0c151b", seaDeep: "#05090c", bandHigh: "#ffd36b",
                marketTop: "#0f0d08", marketBase: "#000000", marketLine: "#2a2824", marketBadge: "#221a08", marketFade: "#080705",
                marketPanel: "#0d0b07", marketText: "#f3eee2", marketMuted: "#a5a29b", marketUpTop: "#0a120c", marketDownTop: "#160807",
                marketMid: "#060605", marketValue: "#fffaf0",
                monoFont: "Inter", voiceFont: "Inter Display", bodyFont: "Inter", caps: true, hudGrid: false }
    })
    readonly property var set: accents[accentName] || accents["apvis"]
    function pick(name, fallback) { return set[name] !== undefined ? set[name] : fallback }

    // Type (V3 M3). V2 uses the system font, "monospace" for labels and UPPER-CASE labels.
    readonly property string monoFont: pick("monoFont", "monospace")
    readonly property string voiceFont: pick("voiceFont", "")      // APVIS's own voice: page titles, answers
    readonly property string bodyFont: pick("bodyFont", "")
    readonly property bool caps: pick("caps", true)
    readonly property bool hudGrid: pick("hudGrid", true)
    readonly property string coreStyle: pick("coreStyle", "smoke")  // "smoke" (V2 planet in energy smoke) | "instrument" (V3 brass) | "hud" (V3 JARVIS light)
    readonly property string wallpaper: pick("wallpaper", "nebula.png")
    readonly property real markGlow: pick("markGlow", 0.8)
    // Lacquer panels: solid lacquer, brass hairlines and bevel, no glass sheen or HUD cuts (V3 look).
    readonly property bool lacquer: pick("panelStyle", "") === "lacquer" || holo
    // Holographic panels (V3 JARVIS look, owner 2026-10-06): cut corners, glowing gold hairlines, brackets.
    readonly property bool holo: pick("panelStyle", "") === "holo"
    // A label as the current direction writes it: V2 keeps the upper case it was written in; a
    // sentence-case direction turns "WAITING FOR YOUR REVIEW" into "Waiting for your review".
    // Text a V2 screen shows in capitals: kept as written in a sentence-case direction.
    function upper(t) { return caps ? String(t).toUpperCase() : String(t) }
    // Names and acronyms that stay in capitals in sentence case.
    readonly property var keepCaps: ["APVIS", "OS", "AI", "UK", "LDN", "ISS", "UTC", "CPU", "RAM", "GPU", "API", "USB", "SSH",
                                     "LAN", "PC", "GB", "MB", "KB", "TB", "URL", "IP", "DNS", "VPN", "OK", "ID", "NASA", "USGS",
                                     "BBC", "TFL", "V2", "V3", "KP", "FPS", "HD", "SSD", "NVME", "HDD", "QR", "TV", "GDACS", "EONET",
                                     "SWPC", "GDELT", "ADS-B", "AIS", "DND", "UEFI", "BIOS"]
    function label(t) {
        if (caps || !t) return t
        const s = String(t)
        if (s !== s.toUpperCase()) return s
        if (/^(?:\S )+\S$/.test(s.trim())) return s                 // spaced letters ("A T L A S"): a wordmark
        const out = s.toLowerCase().replace(/[a-z0-9][a-z0-9-]*/g, w => keepCaps.indexOf(w.toUpperCase()) >= 0 ? w.toUpperCase() : w)
        const i = out.search(/[A-Za-z]/)
        return i < 0 ? out : out.slice(0, i) + out.charAt(i).toUpperCase() + out.slice(i + 1)
    }

    readonly property color accent: set.accent
    readonly property color accentSoft: set.accentSoft
    readonly property color line: set.line
    readonly property color panel: set.panel
    readonly property color raised: set.raised
    readonly property color hover: set.hover
    readonly property color bgTop: set.bgTop
    readonly property color bgMid: set.bgMid
    readonly property color bgBottom: set.bgBottom
    readonly property color text: set.text
    readonly property color muted: set.muted
    readonly property color glow: set.glow
    // Semantic colours are fixed across accents: amber = your attention,
    // red = verified critical error only.
    readonly property color attention: pick("attention", "#e8bc70")
    readonly property color critical: pick("critical", "#e46a5f")
    readonly property color warm: pick("warm", "#f0b36a")

    // ---- V3 M3: every colour the QML uses lives in this file. These are the V2 values, so nothing
    // looks different yet; a V3 direction only has to change this file.
    // Neutrals (used with alpha through shade()/sheen()).
    readonly property color ink: pick("ink", "#000000")            // deepest black: the Home floor and full-screen overlays
    readonly property color accentInk: pick("accentInk", "#000000")       // text and marks drawn on an accent fill
    readonly property color shadeBase: pick("shadeBase", "#000000")      // scrims, vignettes, shadows
    readonly property color sheenBase: pick("sheenBase", "#ffffff")      // hovers, tracks, glints
    readonly property color terminal: pick("terminal", "#010302")       // the Home terminal card
    function shade(a) { return Qt.rgba(shadeBase.r, shadeBase.g, shadeBase.b, a) }
    function sheen(a) { return Qt.rgba(sheenBase.r, sheenBase.g, sheenBase.b, a) }
    function tint(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }
    // A colour (or "#rrggbb" string) at an alpha, as a Canvas style string.
    function css(c, a) {
        const q = typeof c === "string" ? Qt.color(c) : c
        return "rgba(" + Math.round(q.r * 255) + "," + Math.round(q.g * 255) + "," + Math.round(q.b * 255) + "," + a + ")"
    }
    // Information colours (fixed across accents).
    readonly property color info: pick("info", "#7fb6ff")           // research and knowledge
    readonly property color signal: pick("signal", "#5ad1e6")         // a second live signal (balanced tier, storms)
    readonly property color fire: pick("fire", "#ff8a4c")
    readonly property color gain: pick("gain", "#3ddc97")           // markets up
    readonly property color loss: pick("loss", "#ff5f5f")           // markets down
    // The core (defaults for the Nucleus components).
    readonly property color coreTint: pick("coreTint", "#62e3b1")
    readonly property color coreHighlight: pick("coreHighlight", "#eef2f4")
    readonly property color markGlint: pick("markGlint", "#ebfff0")      // the A mark's highlight stroke
    // Atlas.
    readonly property color atlasFloorTop: pick("atlasFloorTop", "#050b0a")
    readonly property color atlasFloorMid: pick("atlasFloorMid", "#030706")
    readonly property color atlasFloorBottom: pick("atlasFloorBottom", "#020403")
    readonly property color atlasGrid: pick("atlasGrid", "#4cc983")
    readonly property color atlasBadgeText: pick("atlasBadgeText", "#04110a")
    readonly property color atlasChipOff: pick("atlasChipOff", "#050d0a")      // layer chips that are off
    readonly property color nightSide: pick("nightSide", "#01040c")      // flat map night shading
    readonly property color globeNight: pick("globeNight", "#00040a")     // globe night side
    readonly property color seaShallow: pick("seaShallow", "#0e3a34")
    readonly property color seaMid: pick("seaMid", "#06201e")
    readonly property color seaDeep: pick("seaDeep", "#020c0c")
    readonly property color sunlight: pick("sunlight", "#ffd68c")
    readonly property color starlight: pick("starlight", "#ffe2aa")      // city lights and labels on the globe's dark side
    readonly property color bandHigh: pick("bandHigh", "#b8f0d8")
    readonly property color kpCalm: pick("kpCalm", "#9fb8ff")
    readonly property color nightLayer: pick("nightLayer", "#8fa8ff")
    readonly property var eventColours: pick("eventColours", { fire: "#ff8a4c", storm: "#5ad1e6", cyclone: "#5ad1e6", volcano: "#e46a5f", ice: "#dfe8ee",
                                           flood: "#6c9cff", drought: "#d9b36a", quake: "#f0b36a", dust: "#c9b08a", iss: "#eef2f4", camera: "#9fd8ff" })
    // Atlas markets panel.
    readonly property color marketTop: pick("marketTop", "#06140e")
    readonly property color marketBase: pick("marketBase", "#010403")
    readonly property color marketLine: pick("marketLine", "#1d3a2c")
    readonly property color marketBadge: pick("marketBadge", "#0b2a1d")
    readonly property color marketFade: pick("marketFade", "#031009")
    readonly property color marketPanel: pick("marketPanel", "#04120c")
    readonly property color marketText: pick("marketText", "#cfeee0")
    readonly property color marketMuted: pick("marketMuted", "#6f8f80")
    readonly property color marketLossTrack: pick("marketLossTrack", "#3a1414")
    readonly property color marketUpTop: pick("marketUpTop", "#06170f")
    readonly property color marketDownTop: pick("marketDownTop", "#170808")
    readonly property color marketMid: pick("marketMid", "#030a07")
    readonly property color marketValue: pick("marketValue", "#e8fff4")
    readonly property color marketPrevious: pick("marketPrevious", "#96aaa0")
    // Other apps' own brand colours (Apps Store tiles); never part of the APVIS look.
    readonly property var brandTints: ({ firefox: "#ff7139", vscode: "#3ea6f2", vlc: "#ff8a00", libreoffice: "#dfe5ea", thunderbird: "#3d8ae6",
                                         obsidian: "#8b6cef", spotify: "#1ed760", discord: "#5865f2", steam: "#66c0f4", gimp: "#c8b89a",
                                         blender: "#ea7600", chromium: "#4c8bf5", telegram: "#2aabee", krita: "#3daee9", inkscape: "#e6e6e6",
                                         obs: "#c0c0c0", audacity: "#f0a000", kdenlive: "#6aa7e8", keepassxc: "#6cac4d", "github-desktop": "#b18bf0",
                                         mpv: "#9c5dc9", transmission: "#d0302f", filezilla: "#bf0000", syncthing: "#0891d1", docker: "#1d91e6",
                                         nextcloud: "#0082c9" })
}
