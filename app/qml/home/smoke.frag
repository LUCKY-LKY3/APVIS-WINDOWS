// Volumetric emerald smoke around the Nucleus: domain-warped fractal noise that
// swirls slowly around the core, densest in a band hugging the sphere, with
// brighter curling tendrils. uFront = 1 draws only the tendrils that wrap in
// front of the sphere's rim (depth by occlusion); 0 draws the back volume.
// The quad covers a square around the core (see Smoke.qml); uSpan converts
// its coordinates back to screen-height units so the noise keeps its size.
VARYING vec2 vUV;

float hash(vec2 p)
{
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float noise(vec2 p)
{
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
               mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float fbm(vec2 p, int octaves)
{
    float v = 0.0;
    float a = 0.5;
    mat2 rot = mat2(0.8, -0.6, 0.6, 0.8);
    for (int i = 0; i < 4; ++i) {
        if (i >= octaves) break;
        v += a * noise(p);
        p = rot * p * 2.03 + vec2(1.7, 9.2);
        a *= 0.5;
    }
    return v;
}

void MAIN()
{
    vec2 local = vec2(vUV.x, 1.0 - vUV.y) - 0.5;
    vec2 p = local * uSpan;
    float r = length(p);
    float band = exp(-pow((r - uRadius) / (uRadius * 0.34), 2.0));
    // Soft edge so the square region never shows.
    float edge = 1.0 - smoothstep(0.36, 0.5, length(local));
    if (edge <= 0.0 || (uFront > 0.5 && band < 0.02)) {
        FRAGCOLOR = vec4(0.0);
        return;
    }
    float t = uTime * 0.035;
    // Swirl: rotate sample space around the core, faster near it.
    float swirl = 0.9 / (0.35 + r * 2.5);
    float ang = t * swirl;
    mat2 spin = mat2(cos(ang), -sin(ang), sin(ang), cos(ang));
    vec2 s = spin * p * 2.6;
    vec2 q = vec2(fbm(s + vec2(0.0, t), 2), fbm(s + vec2(5.2, 1.3) - t, 2));
    float f = fbm(s + 1.8 * q + vec2(t * 0.6, -t * 0.4), 4);

    float field = 0.55 * exp(-r * 1.1);           // general haze around the core
    float wisps = smoothstep(0.30, 0.80, f);
    float tendril = pow(smoothstep(0.52, 0.85, f), 2.0);

    vec3 deep = uGlow.rgb;
    vec3 body = uTint.rgb;
    vec3 col = mix(deep, body, clamp(f * 1.2 - 0.2, 0.0, 1.0));
    col = mix(col, uSilver.rgb, tendril * 0.35);
    // Light from the core: smoke nearer the sphere is lit brighter.
    col *= 1.3 + 1.8 * exp(-pow(max(r - uRadius * 0.9, 0.0) / (uRadius * 0.6), 2.0));

    float a;
    if (uFront > 0.5) {
        // Only thin tendrils, only in the rim band, kept away from the centre text.
        a = tendril * band * 0.9 * smoothstep(uRadius * 0.62, uRadius * 0.9, r);
    } else {
        float inner = smoothstep(uRadius * 0.25, uRadius * 0.95, r);   // keep the core itself clear
        a = (wisps * (band * 0.95 + field) + tendril * band * 0.5) * mix(0.35, 1.0, inner);
    }
    a = clamp(a * uStrength * edge, 0.0, 0.9);
    FRAGCOLOR = vec4(col * a, a);
}
