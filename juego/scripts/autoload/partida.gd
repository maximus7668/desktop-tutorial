extends Node

## Ajustes de la partida en curso y mapa de controles.

var luchador_jugador := "ren"
var luchador_rival := "yuki"
var dificultad := "normal"  # facil, normal, dificil

# Controles por defecto. Si defines una acción en el editor (Proyecto > Ajustes > Mapa de entrada),
# se respeta la tuya y esta no se toca.
const ACCIONES := {
	"adelante": {"teclas": [KEY_W, KEY_UP], "eje": [JOY_AXIS_LEFT_Y, -1.0]},
	"atras": {"teclas": [KEY_S, KEY_DOWN], "eje": [JOY_AXIS_LEFT_Y, 1.0]},
	"izquierda": {"teclas": [KEY_A, KEY_LEFT], "eje": [JOY_AXIS_LEFT_X, -1.0]},
	"derecha": {"teclas": [KEY_D, KEY_RIGHT], "eje": [JOY_AXIS_LEFT_X, 1.0]},
	"subir": {"teclas": [KEY_SPACE], "boton": JOY_BUTTON_RIGHT_SHOULDER},
	"bajar": {"teclas": [KEY_CTRL, KEY_C], "boton": JOY_BUTTON_LEFT_SHOULDER},
	"impulso": {"teclas": [KEY_SHIFT], "boton": JOY_BUTTON_A},
	"golpe": {"teclas": [KEY_J], "boton": JOY_BUTTON_X},
	"ki": {"teclas": [KEY_K], "boton": JOY_BUTTON_Y},
	"guardia": {"teclas": [KEY_L], "boton": JOY_BUTTON_B},
	"cargar": {"teclas": [KEY_U], "eje": [JOY_AXIS_TRIGGER_LEFT, 1.0]},
	"super": {"teclas": [KEY_I], "eje": [JOY_AXIS_TRIGGER_RIGHT, 1.0]},
	"pausa": {"teclas": [KEY_ESCAPE, KEY_P], "boton": JOY_BUTTON_START},
}

# Texto para la pantalla de controles: [acción, teclado, mando].
const AYUDA := [
	["Moverse alrededor del rival", "W A S D", "Stick izquierdo"],
	["Subir / bajar", "Espacio / Ctrl", "RB / LB"],
	["Paso rápido (pulsar) · Correr (mantener)", "Shift", "A"],
	["Combo cuerpo a cuerpo (pulsar varias veces)", "J", "X"],
	["Golpe fuerte (mantener y soltar)", "J mantenido", "X mantenido"],
	["Ráfaga de ki", "K", "Y"],
	["Guardia", "L", "B"],
	["Cargar ki", "U", "LT"],
	["Súper ataque (2 barras de ki)", "I", "RT"],
	["Pausa", "Esc", "Start"],
]


func _ready() -> void:
	registrar_controles()


func registrar_controles() -> void:
	for accion: String in ACCIONES:
		if InputMap.has_action(accion) and not InputMap.action_get_events(accion).is_empty():
			continue
		if not InputMap.has_action(accion):
			InputMap.add_action(accion, 0.3)
		var d: Dictionary = ACCIONES[accion]
		for tecla: int in d.get("teclas", []):
			var evento_tecla := InputEventKey.new()
			evento_tecla.physical_keycode = tecla
			InputMap.action_add_event(accion, evento_tecla)
		if d.has("boton"):
			var evento_boton := InputEventJoypadButton.new()
			evento_boton.button_index = d["boton"]
			InputMap.action_add_event(accion, evento_boton)
		if d.has("eje"):
			var evento_eje := InputEventJoypadMotion.new()
			evento_eje.axis = d["eje"][0]
			evento_eje.axis_value = d["eje"][1]
			InputMap.action_add_event(accion, evento_eje)
