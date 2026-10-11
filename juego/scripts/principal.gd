extends Node

## Pantallas del juego: título (con un combate de demostración detrás), selección,
## controles, combate, pausa y resultado.

const ORO := Color(1.0, 0.82, 0.25)
const TINTA := Color(0.97, 0.94, 0.9)
const FONDO := Color(0.07, 0.05, 0.13, 0.78)

var combate: Combate = null
var ui: CanvasLayer
var pantalla := ""
var _seleccion := {"jugador": "ren", "rival": "yuki", "dificultad": "normal"}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	ui = CanvasLayer.new()
	ui.layer = 10
	add_child(ui)
	_titulo()


func _unhandled_input(evento: InputEvent) -> void:
	if evento.is_action_pressed("pausa"):
		if pantalla == "combate":
			_pausar(true)
		elif pantalla == "pausa":
			_pausar(false)
		elif pantalla in ["seleccion", "controles"]:
			_titulo()
		get_viewport().set_input_as_handled()


# --- pantallas ---------------------------------------------------------------------------------

func _titulo() -> void:
	pantalla = "titulo"
	get_tree().paused = false
	_nuevo_combate(_azar_personaje(), _azar_personaje(), ControlCPU.new("normal", randi()), ControlCPU.new("normal", randi()), {"demo": true, "hud": false, "tiempo": 9999.0})
	var caja := _panel_central(560)
	var titulo := _etiqueta(caja, "RYŪSEI CLASH", 72, ORO, 18)
	titulo.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var sub := _etiqueta(caja, "流星クラッシュ", 24, Color(0.37, 0.85, 1.0), 6)
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var fuente_jp := SystemFont.new()
	fuente_jp.font_names = PackedStringArray(["Noto Sans CJK JP", "Yu Gothic", "Meiryo", "MS Gothic", "Hiragino Sans", "Noto Sans JP"])
	sub.label_settings.font = fuente_jp
	_espacio(caja, 16)
	var empezar := _boton(caja, "Combate contra la CPU", _seleccionar)
	_boton(caja, "Controles", _controles)
	_boton(caja, "Salir", func() -> void: get_tree().quit())
	empezar.grab_focus()


func _seleccionar() -> void:
	pantalla = "seleccion"
	_limpiar_ui()
	var caja := _panel_central(760)
	_etiqueta(caja, "ELIGE TU LUCHADOR", 40, ORO, 10).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var filas := HBoxContainer.new()
	filas.add_theme_constant_override("separation", 24)
	filas.alignment = BoxContainer.ALIGNMENT_CENTER
	caja.add_child(filas)
	var primero: Button = null
	for papel: String in ["jugador", "rival"]:
		var columna := VBoxContainer.new()
		columna.custom_minimum_size = Vector2(330, 0)
		columna.add_theme_constant_override("separation", 8)
		filas.add_child(columna)
		_etiqueta(columna, "Tú" if papel == "jugador" else "Rival (CPU)", 24, TINTA, 6)
		var grupo := ButtonGroup.new()
		for id: String in Personajes.ids():
			var datos := Personajes.datos(id)
			var b := _boton(columna, "%s  ·  %s" % [datos["nombre"], datos["estilo"]], func() -> void: _seleccion[papel] = id)
			b.toggle_mode = true
			b.button_group = grupo
			b.button_pressed = _seleccion[papel] == id
			if primero == null:
				primero = b
	_espacio(caja, 8)
	_etiqueta(caja, "Dificultad", 24, TINTA, 6)
	var dificultades := HBoxContainer.new()
	dificultades.alignment = BoxContainer.ALIGNMENT_CENTER
	dificultades.add_theme_constant_override("separation", 10)
	caja.add_child(dificultades)
	var grupo_dificultad := ButtonGroup.new()
	for opcion: Array in [["facil", "Fácil"], ["normal", "Normal"], ["dificil", "Difícil"]]:
		var b := _boton(dificultades, opcion[1], func() -> void: _seleccion["dificultad"] = opcion[0])
		b.toggle_mode = true
		b.button_group = grupo_dificultad
		b.button_pressed = _seleccion["dificultad"] == opcion[0]
		b.custom_minimum_size = Vector2(150, 48)
	_espacio(caja, 12)
	_boton(caja, "¡A pelear!", _empezar_combate)
	_boton(caja, "Volver", _titulo)
	if primero != null:
		primero.grab_focus()


func _controles() -> void:
	pantalla = "controles"
	_limpiar_ui()
	var caja := _panel_central(820)
	_etiqueta(caja, "CONTROLES", 40, ORO, 10).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var tabla := GridContainer.new()
	tabla.columns = 3
	tabla.add_theme_constant_override("h_separation", 28)
	tabla.add_theme_constant_override("v_separation", 6)
	caja.add_child(tabla)
	for cabecera: String in ["Acción", "Teclado", "Mando"]:
		_etiqueta(tabla, cabecera, 20, ORO, 4)
	for fila: Array in Partida.AYUDA:
		for celda: String in fila:
			_etiqueta(tabla, celda, 18, TINTA, 4)
	_espacio(caja, 8)
	var nota := _etiqueta(caja, "Pulsa el paso rápido justo antes de que te golpeen: si tienes media barra de ki, te teletransportas detrás del rival.", 18, Color(0.37, 0.85, 1.0), 4)
	nota.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	nota.custom_minimum_size = Vector2(760, 0)
	_boton(caja, "Volver", _titulo).grab_focus()


func _empezar_combate() -> void:
	Partida.luchador_jugador = _seleccion["jugador"]
	Partida.luchador_rival = _seleccion["rival"]
	Partida.dificultad = _seleccion["dificultad"]
	pantalla = "combate"
	_limpiar_ui()
	_nuevo_combate(Partida.luchador_jugador, Partida.luchador_rival, ControlJugador.new(), ControlCPU.new(Partida.dificultad, randi()), {})
	combate.terminado.connect(_resultado)


func _pausar(activar: bool) -> void:
	if combate == null:
		return
	if activar:
		pantalla = "pausa"
		combate.pausado = true
		Sonidos.parar_todo()
		var caja := _panel_central(480)
		_etiqueta(caja, "PAUSA", 48, ORO, 12).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		_boton(caja, "Seguir", func() -> void: _pausar(false)).grab_focus()
		_boton(caja, "Reiniciar combate", _empezar_combate)
		_boton(caja, "Salir al menú", _titulo)
	else:
		pantalla = "combate"
		combate.pausado = false
		_limpiar_ui()


func _resultado(ganador: Luchador) -> void:
	pantalla = "resultado"
	_limpiar_ui()
	var caja := _panel_central(640)
	var texto := "EMPATE"
	var frase := ""
	if ganador != null:
		texto = "GANA %s" % str(ganador.def["nombre"]).to_upper()
		frase = "«%s»" % ganador.def["frases"]["victoria"]
	var titulo := _etiqueta(caja, texto, 52, ORO, 14)
	titulo.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	if not frase.is_empty():
		var cita := _etiqueta(caja, frase, 22, TINTA, 4)
		cita.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		cita.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_espacio(caja, 10)
	_boton(caja, "Revancha", _empezar_combate).grab_focus()
	_boton(caja, "Cambiar luchadores", _seleccionar)
	_boton(caja, "Menú principal", _titulo)


# --- utilidades ----------------------------------------------------------------------------------

func _nuevo_combate(a: String, b: String, control_a: Variant, control_b: Variant, opciones: Dictionary) -> void:
	if combate != null:
		combate.queue_free()
		combate = null
	Sonidos.parar_todo()
	_limpiar_ui()
	combate = Combate.new()
	combate.name = "Combate"
	add_child(combate)
	combate.process_mode = Node.PROCESS_MODE_PAUSABLE
	combate.preparar(a, b, control_a, control_b, opciones)
	if opciones.get("demo", false):
		combate.terminado.connect(func(_g: Luchador) -> void:
			if pantalla in ["titulo", "controles"]:
				_titulo.call_deferred())


func _azar_personaje() -> String:
	var ids := Personajes.ids()
	return ids[randi() % ids.size()]


func _limpiar_ui() -> void:
	for hijo in ui.get_children():
		hijo.queue_free()


func _panel_central(ancho: int) -> VBoxContainer:
	_limpiar_ui()
	var centro := CenterContainer.new()
	centro.set_anchors_preset(Control.PRESET_FULL_RECT)
	ui.add_child(centro)
	var panel := PanelContainer.new()
	var estilo := StyleBoxFlat.new()
	estilo.bg_color = FONDO
	estilo.border_color = ORO
	estilo.set_border_width_all(2)
	estilo.set_corner_radius_all(6)
	estilo.set_content_margin_all(28)
	panel.add_theme_stylebox_override("panel", estilo)
	panel.custom_minimum_size = Vector2(ancho, 0)
	centro.add_child(panel)
	var caja := VBoxContainer.new()
	caja.add_theme_constant_override("separation", 10)
	panel.add_child(caja)
	return caja


func _etiqueta(padre: Control, texto: String, tam: int, color: Color, contorno: int) -> Label:
	var etiqueta := Label.new()
	etiqueta.text = texto
	var ajustes := LabelSettings.new()
	ajustes.font_size = tam
	ajustes.font_color = color
	ajustes.outline_size = contorno
	ajustes.outline_color = Color(0.07, 0.04, 0.12)
	etiqueta.label_settings = ajustes
	padre.add_child(etiqueta)
	return etiqueta


func _boton(padre: Control, texto: String, accion: Callable) -> Button:
	var b := Button.new()
	b.text = texto
	b.custom_minimum_size = Vector2(0, 52)
	b.add_theme_font_size_override("font_size", 22)
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.16, 0.12, 0.28)
	normal.set_corner_radius_all(4)
	normal.set_content_margin_all(10)
	var resaltado := normal.duplicate() as StyleBoxFlat
	resaltado.bg_color = Color(1.0, 0.55, 0.2)
	var pulsado := normal.duplicate() as StyleBoxFlat
	pulsado.bg_color = ORO
	b.add_theme_stylebox_override("normal", normal)
	b.add_theme_stylebox_override("hover", resaltado)
	b.add_theme_stylebox_override("focus", resaltado)
	b.add_theme_stylebox_override("pressed", pulsado)
	b.add_theme_color_override("font_pressed_color", Color(0.07, 0.04, 0.12))
	b.add_theme_color_override("font_hover_color", Color(0.07, 0.04, 0.12))
	b.add_theme_color_override("font_focus_color", Color(0.07, 0.04, 0.12))
	b.pressed.connect(func() -> void:
		Sonidos.tocar("menu")
		accion.call())
	padre.add_child(b)
	return b


func _espacio(padre: Control, alto: int) -> void:
	var hueco := Control.new()
	hueco.custom_minimum_size = Vector2(0, alto)
	padre.add_child(hueco)
