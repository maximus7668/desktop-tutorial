// Cel-shading estilo anime: luz y sombra en dos tonos con borde duro, sombra tintada
// (no negra) y un brillo fino en el contorno del lado iluminado.
shader_type spatial;
render_mode cull_back;

uniform vec4 color_base : source_color = vec4(1.0);
// Degradado hacia la punta (para mechones de pelo). Alturas en espacio local del objeto.
uniform vec4 color_punta : source_color = vec4(1.0);
uniform float punta_desde = 100.0;
uniform float punta_hasta = 101.0;
// Multiplicador de color en la zona de sombra.
uniform vec4 color_sombra : source_color = vec4(0.62, 0.55, 0.82, 1.0);
uniform float umbral : hint_range(-1.0, 1.0) = 0.08;
uniform float suavidad : hint_range(0.0, 0.5) = 0.03;
uniform float brillo_borde : hint_range(0.0, 2.0) = 0.45;
uniform float ancho_borde : hint_range(0.0, 1.0) = 0.28;
uniform float emision = 0.0;

varying float altura_local;

void vertex() {
	altura_local = VERTEX.y;
}

void fragment() {
	float k = clamp((altura_local - punta_desde) / max(punta_hasta - punta_desde, 0.0001), 0.0, 1.0);
	vec3 c = mix(color_base.rgb, color_punta.rgb, k);
	ALBEDO = c;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
	EMISSION = c * emision;
}

void light() {
	float ndl = dot(NORMAL, LIGHT);
	float banda = smoothstep(umbral - suavidad, umbral + suavidad, ndl) * step(0.5, ATTENUATION);
	vec3 tono = mix(color_sombra.rgb, vec3(1.0), banda);
	DIFFUSE_LIGHT += tono * LIGHT_COLOR / PI;
	float borde = 1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0);
	borde = smoothstep(1.0 - ancho_borde, 1.0 - ancho_borde + 0.04, borde) * banda;
	SPECULAR_LIGHT += borde * brillo_borde * ALBEDO * LIGHT_COLOR / PI;
}
