// Soft round particle, premultiplied for additive blending.
VARYING vec2 vUV;
VARYING float vGlow;
VARYING float vSpark;
VARYING float vDepth;

void MAIN()
{
    vec2 c = vUV * 2.0 - 1.0;
    float r2 = dot(c, c);
    if (r2 > 1.0)
        discard;
    float a = exp(-r2 * 3.2) * vGlow;
    // Far particles sink into a deeper tint; the nearest pick up a little silver.
    vec3 body = mix(uTint.rgb * 0.55, uTint.rgb, smoothstep(0.0, 0.7, vDepth));
    body = mix(body, uHighlight.rgb, 0.30 * smoothstep(0.78, 1.0, vDepth));
    vec3 colour = mix(body, uWarm.rgb, vSpark);
    FRAGCOLOR = vec4(colour * a, a);
}
