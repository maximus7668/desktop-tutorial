// Energía (auras, ráfagas de ki y rayos): brilla más en los bordes, con bandas que se desplazan.
// Se suma a la imagen, así que los valores altos se ven como resplandor con el glow del entorno.
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled;

uniform vec4 color : source_color = vec4(1.0, 0.55, 0.2, 1.0);
uniform vec4 color_nucleo : source_color = vec4(1.0, 0.97, 0.85, 1.0);
uniform float intensidad = 1.6;
uniform float velocidad = 2.5;
uniform float bandas = 6.0;
uniform float poder_borde = 1.6;
uniform float opacidad : hint_range(0.0, 1.0) = 1.0;
// Opacidad en el centro del objeto (de frente); el borde siempre brilla más.
uniform float centro : hint_range(0.0, 1.0) = 0.35;

void fragment() {
	float borde = pow(1.0 - clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0), poder_borde);
	float onda = sin((UV.y * bandas - TIME * velocidad) * 6.2831) * 0.5 + 0.5;
	vec3 c = mix(color_nucleo.rgb, color.rgb, clamp(borde * 1.4, 0.0, 1.0));
	ALBEDO = c * intensidad;
	ALPHA = clamp((0.45 + 0.55 * onda) * (centro + borde) * opacidad, 0.0, 1.0);
}
