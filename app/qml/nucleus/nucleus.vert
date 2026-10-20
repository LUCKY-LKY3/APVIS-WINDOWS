// APVIS Nucleus particle vertex shader (Qt Quick 3D custom material).
// Instance translation = unit-sphere target; INSTANCE_DATA = globe target + seed;
// INSTANCE_COLOR = (spark, ocean, unused, brightness). All motion is computed
// here so no per-particle work runs in Python or JavaScript.
VARYING vec2 vUV;
VARYING float vGlow;
VARYING float vSpark;
VARYING float vDepth;

vec3 rotateY(vec3 p, float a)
{
    float c = cos(a);
    float s = sin(a);
    return vec3(p.x * c + p.z * s, p.y, -p.x * s + p.z * c);
}

vec3 rotateX(vec3 p, float a)
{
    float c = cos(a);
    float s = sin(a);
    return vec3(p.x, p.y * c - p.z * s, p.y * s + p.z * c);
}

void MAIN()
{
    vec3 sphere = INSTANCE_MODEL_MATRIX[3].xyz;
    vec3 globe = INSTANCE_DATA.xyz;
    float seed = INSTANCE_DATA.w;
    float spark = INSTANCE_COLOR.r;
    float ocean = INSTANCE_COLOR.g;
    float bright = INSTANCE_COLOR.a;

    // Living sphere: slow differential swirl, breathing and gentle turbulence.
    vec3 s = rotateY(sphere, uTime * uOrbit * (seed - 0.5) * 0.8);
    float wobble = sin(uTime * (0.6 + seed * 1.4) + seed * 6.2831) * uTurbulence * 0.05;
    s *= 1.0 + uBreath + wobble;

    // Shape morphs share the same particles.
    vec3 p = mix(s, globe * 1.02, uGlobe);
    p = rotateX(rotateY(p, uYaw), uPitch);

    // Answer Focus: part the particles into a ring around a clear reading plane.
    float d = length(p.xy);
    vec2 dir = d > 0.0001 ? p.xy / d : vec2(cos(seed * 6.2831), sin(seed * 6.2831));
    float ring = 1.10 + 0.24 * fract(seed * 7.13);
    p.xy = mix(p.xy, dir * max(d, ring), uAperture);
    p.z *= 1.0 - 0.8 * uAperture;

    // Clear core: keep the wordmark readable; displaced particles form a dense
    // luminous band hugging the core (not used by the globe).
    float clearR = uClear * (1.0 - uGlobe) * (1.0 - uAperture);
    float dc = length(p.xy);
    if (dc < clearR)
        p.xy = dir * (clearR + (dc / max(clearR, 0.0001)) * 0.09);
    float limb = 0.72 + 0.55 * smoothstep(0.55, 1.0, length(p.xy));

    vec4 clip = VIEWPROJECTION_MATRIX * vec4(p * uRadius, 1.0);
    float depth = clamp(p.z * 0.5 + 0.5, 0.0, 1.0);
    // Depth reads as volume: the far side is smaller and much dimmer.
    float size = uSizePx * (0.40 + 1.05 * depth) * (spark > 0.5 ? 1.6 : 1.0);
    clip.xy += (VERTEX.xy / 50.0) * size * 2.0 / uViewport * clip.w;

    float near = pow(depth, 1.4);
    // Rim light: the silhouette catches light, mostly on the side facing the viewer.
    float rim = smoothstep(0.78, 1.0, length(p.xy)) * (0.35 + 0.65 * depth);
    float glow = bright * mix(0.10, 1.0, near) * uEnergy * limb * (1.0 + 0.55 * rim * (1.0 - uGlobe));
    glow *= mix(1.0, mix(1.0, 0.25, ocean), uGlobe);
    vUV = UV0;
    vGlow = glow;
    vSpark = spark * (1.0 - uGlobe);
    vDepth = mix(depth, 0.7, uAperture);
    POSITION = clip;
}
