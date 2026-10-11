// Contorno negro de dibujo animado: una segunda pasada del modelo, inflada y vista por dentro.
shader_type spatial;
render_mode unshaded, cull_front, depth_draw_opaque;

uniform vec4 color : source_color = vec4(0.06, 0.04, 0.1, 1.0);
uniform float grosor = 0.014;

void vertex() {
	VERTEX += NORMAL * grosor;
}

void fragment() {
	ALBEDO = color.rgb;
}
