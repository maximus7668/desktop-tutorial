// Suelo de la arena: manchas de hierba y tierra con borde duro, y el mismo sombreado en dos tonos.
shader_type spatial;

uniform vec4 color_hierba : source_color = vec4(0.40, 0.62, 0.30, 1.0);
uniform vec4 color_tierra : source_color = vec4(0.72, 0.60, 0.42, 1.0);
uniform vec4 color_roca : source_color = vec4(0.55, 0.50, 0.48, 1.0);
uniform vec4 color_sombra : source_color = vec4(0.62, 0.55, 0.82, 1.0);
uniform float escala = 0.028;

varying vec3 pos_mundo;

float azar(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float ruido(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(azar(i), azar(i + vec2(1.0, 0.0)), u.x), mix(azar(i + vec2(0.0, 1.0)), azar(i + vec2(1.0, 1.0)), u.x), u.y);
}

void vertex() {
	pos_mundo = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 p = pos_mundo.xz * escala;
	float n = ruido(p) * 0.6 + ruido(p * 3.1) * 0.3 + ruido(p * 9.7) * 0.1;
	float tierra = step(0.56, n);
	float roca = step(0.74, ruido(p * 2.3 + 17.0) * 0.7 + ruido(p * 7.0) * 0.3);
	vec3 c = mix(color_hierba.rgb, color_tierra.rgb, tierra);
	c = mix(c, color_roca.rgb, roca * tierra);
	ALBEDO = c;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
}

void light() {
	float banda = smoothstep(0.05, 0.11, dot(NORMAL, LIGHT)) * step(0.5, ATTENUATION);
	DIFFUSE_LIGHT += mix(color_sombra.rgb, vec3(1.0), banda) * LIGHT_COLOR / PI;
}
