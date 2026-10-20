// JARVIS core (owner's reference images, 2026-10-20: "more particley", then "remove the outer
// particles, add more"): a dense cloud of glinting particles in nested, counter-turning
// shells with a ragged edge.
// All on the GPU; the quad covers a square around the core and p is in units
// of the outer halo radius.
VARYING vec2 vUV;

float hash(vec2 p)
{
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

vec3 hash33(vec3 p)
{
    p = fract(p * vec3(0.1031, 0.1030, 0.0973));
    p += dot(p, p.yxz + 33.33);
    return fract((p.xxy + p.yxx) * p.zyx);
}

float noise(vec2 p)
{
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
               mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float fbm(vec2 p)
{
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 4; ++i) {
        v += a * noise(p);
        p = p * 2.03 + vec2(17.1, 9.2);
        a *= 0.5;
    }
    return v;
}

vec3 spin(vec3 n, float yaw, float tilt)
{
    float c = cos(yaw);
    float s = sin(yaw);
    n = vec3(c * n.x + s * n.z, n.y, -s * n.x + c * n.z);
    c = cos(tilt);
    s = sin(tilt);
    return vec3(n.x, c * n.y - s * n.z, s * n.y + c * n.z);
}

// Particles on a sphere: the surface point is scaled into a 3D grid; each cell
// holds one particle at a random spot, drawn as a soft dot where the surface
// passes near it (so sizes vary naturally). Returns brightness.
float specks(vec3 n, float k, float t, float seed)
{
    vec3 q = n * k;
    vec3 c = floor(q);
    float b = 0.0;
    for (int i = 0; i < 2; ++i) {
        vec3 cc = c + vec3(float(i) * 0.5);
        vec3 h = hash33(cc + seed);
        vec3 at = floor(q - float(i) * 0.5) + float(i) * 0.5 + 0.2 + 0.6 * h;
        float d = length(q - at);
        float tw = 0.55 + 0.45 * sin(t * (0.8 + 2.4 * h.x) + h.y * 40.0);
        // a crisp point with a faint halo, so each particle reads on its own (owner: "more defined")
        b += (smoothstep(0.24, 0.11, d) * 2.3 + smoothstep(0.42, 0.0, d) * 0.25) * tw * (0.6 + h.z);
    }
    return b;
}

// One shell of the cloud: particles on a sphere of radius sr (in core units),
// front and back, turning at its own rate.
vec3 shell(vec2 p, float sr, float k, float yaw, float tilt, float seed, float t, vec3 tint, vec3 hi)
{
    float rr = length(p) / sr;
    if (rr >= 1.0)
        return vec3(0.0);
    float z = sqrt(1.0 - rr * rr);
    float f = specks(spin(vec3(p / sr, z), yaw, tilt), k, t, seed);
    float b = specks(spin(vec3(p / sr, -z), yaw, tilt), k, t, seed);
    float edge = 0.7 + 0.6 * pow(rr, 3.0);            // denser-looking toward the rim, like a real ball of points
    return (tint * (f + 0.35 * b) + hi * f * f * 0.45) * edge;
}

void MAIN()
{
    vec2 p = (vUV - 0.5) * 2.0 * uExtent;
    float r = length(p);
    float t = uTime;
    float e = uEnergy;
    // darker and bluer than the references so it sits in the dark dashboard (owner, 2026-10-20)
    vec3 tint = mix(uTint.rgb, vec3(0.12, 0.62, 1.0), 0.35) * 0.85;
    vec3 hi = mix(uHi.rgb, vec3(0.6, 0.85, 1.0), 0.4) * 0.8;
    float s = 0.53 * (1.0 + 0.03 * e * sin(t * 3.0));
    float yaw = t * (0.10 + 0.45 * e);
    vec3 col = vec3(0.0);

    // a faint glow inside the cloud
    col += tint * 0.03 * smoothstep(s * 1.02, 0.0, r);
    // nested shells give the cloud its depth; the outer two are sparse and make the ragged edge
    col += shell(p, s * 1.05, 26.0, yaw * 0.8, 0.30, 11.0, t, tint, hi) * 0.6;
    col += shell(p, s * 1.00, 30.0, yaw, 0.35, 1.0, t, tint, hi) * 1.2;
    col += shell(p, s * 0.88, 26.0, -yaw * 1.2, -0.4, 3.0, t, tint, hi) * 0.8;
    col += shell(p, s * 0.68, 20.0, yaw * 1.4, 0.6, 5.0, t, tint, hi) * 0.5;
    col *= 1.0 + 0.6 * e;

    // ---- the HUD frame: thin rings, fine ticks, four cardinal marks and a turning arc
    float ang = atan(p.y, p.x);
    vec3 line = mix(uTint.rgb, vec3(0.16, 0.86, 1.0), 0.5);
    col += line * exp(-pow(r - 0.64, 2.0) / 0.00001) * 0.55;
    col += line * exp(-pow(r - 0.75, 2.0) / 0.000007) * 0.30;
    float tick = step(0.85, fract(ang / 6.2831853 * 120.0));
    col += line * tick * step(0.66, r) * step(r, 0.69) * 0.40;
    float major = step(0.96, fract(ang / 6.2831853 * 12.0 + 0.02));
    col += line * major * step(0.66, r) * step(r, 0.715) * 0.55;
    float card = step(0.9995, abs(cos(ang * 2.0)));
    col += hi * card * step(0.76, r) * step(r, 0.81) * 0.8;
    float arc = fract((ang + t * (0.08 + 0.4 * e)) / 6.2831853);
    col += hi * step(arc, 0.16) * exp(-pow(r - 0.785, 2.0) / 0.000008) * 0.75;
    col += line * step(0.5, arc) * step(arc, 0.56) * exp(-pow(r - 0.785, 2.0) / 0.000008) * 0.45;

    col *= uStrength;

    float alpha = clamp(max(col.r, max(col.g, col.b)), 0.0, 1.0);
    FRAGCOLOR = vec4(col, alpha);
}
