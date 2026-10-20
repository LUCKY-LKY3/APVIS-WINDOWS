// Full-screen pass: the built-in #Rectangle spans -50..50, mapped straight to clip space.
VARYING vec2 vUV;

void MAIN()
{
    vUV = UV0;
    POSITION = vec4(VERTEX.xy / 50.0, 0.0, 1.0);
}
