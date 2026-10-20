// The Intelligence globe's base on the GPU (APVIS for Windows, so it turns at the display's rate): land,
// coastlines and borders from a baked equirectangular mask (art/world-mask.png: R land, G coast, B borders),
// the graticule, the night side with its twilight line, and the sphere's shading. Events, satellites and
// labels stay in the Canvas above. p is in globe radii; the inverse rotation matches AtlasGlobe.unproject().
VARYING vec2 vUV;

float gridLine(float v, float step)
{
    float x = v / step;
    float w = fwidth(x);
    return 1.0 - smoothstep(0.0, w * 1.2, abs(fract(x + 0.5) - 0.5));
}

void MAIN()
{
    vec2 p = (vUV - 0.5) * 2.0 * uExtent;
    float rr = dot(p, p);
    if (rr > 1.0) {
        FRAGCOLOR = vec4(0.0);
        return;
    }
    float z2 = sqrt(1.0 - rr);
    float a = radians(uLon0);
    float ph = radians(uLat0);
    float y = p.y * cos(ph) + z2 * sin(ph);
    float z1 = -p.y * sin(ph) + z2 * cos(ph);
    float x = p.x * cos(a) + z1 * sin(a);
    float z = -p.x * sin(a) + z1 * cos(a);
    float lon = degrees(atan(x, z));
    float lat = degrees(asin(clamp(y, -1.0, 1.0)));
    vec4 m = texture(uLand, vec2(lon / 360.0 + 0.5, 0.5 + lat / 180.0));   // Quick3D textures start at the bottom row

    // premultiplied layers, painted bottom to top with "over"
    vec4 col = vec4(0.0);
    float hl = clamp(length(p - vec2(-0.35, 0.4)) / 1.1, 0.0, 1.0);
    float landA = m.r * mix(0.62, 0.34, hl);
    col = vec4(uAccent.rgb * landA, landA);
    float g = max(gridLine(lon, 30.0), gridLine(lat, 30.0) * step(abs(lat), 61.0)) * 0.13 * (1.0 - m.r * 0.5);
    col = vec4(uAccent.rgb * g, g) + col * (1.0 - g);
    float coast = m.g * 0.75;
    col = vec4(uText.rgb * coast, coast) + col * (1.0 - coast);
    float bord = m.b * (1.0 - m.g) * 0.28;
    col = vec4(uText.rgb * bord, bord) + col * (1.0 - bord);

    // night side and the twilight line
    if (uNightOn > 0.5) {
        float d = dot(vec3(x, y, z), uSun.xyz);
        float night = smoothstep(0.02, -0.02, d) * 0.58;
        col = vec4(uNight.rgb * night, night) + col * (1.0 - night);
        float tw = (1.0 - smoothstep(0.0, fwidth(d) * 1.5, abs(d))) * 0.35;
        col = vec4(uWarm.rgb * tw, tw) + col * (1.0 - tw);
    }
    // a soft highlight up-left and the limb darkening
    float sheen = (1.0 - smoothstep(0.0, 0.9, length(p - vec2(-0.4, 0.45)))) * 0.08;
    col = vec4(uSheen.rgb * sheen, sheen) + col * (1.0 - sheen);
    float limb = smoothstep(0.62, 1.0, sqrt(rr)) * 0.5;
    col = vec4(uShade.rgb * limb, limb) + col * (1.0 - limb);
    // antialiased rim
    col *= 1.0 - smoothstep(1.0 - fwidth(rr) * 1.5, 1.0, rr);
    FRAGCOLOR = col;
}
