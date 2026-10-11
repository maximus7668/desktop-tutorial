class_name Hud
extends CanvasLayer

## Interfaz del combate: vida en tres tramos, ki en cinco barras, tiempo, combos,
## avisos y el medidor del choque de rayos.

const ANCHO_VIDA := 460.0
const ALTO_VIDA := 22.0
const HUECO := 6.0
const ORO := Color(1.0, 0.82, 0.25)
const TINTA := Color(0.97, 0.94, 0.9)
const FONDO := Color(0.07, 0.05, 0.13, 0.85)

var combate: Combate
var lienzo: Control
var _fantasma := [0.0, 0.0]
var _nombres: Array[Label] = []
var _combos: Array[Label] = []
var _avisos: Array[Label] = []
var _aviso_t := [0.0, 0.0]
var _tiempo: Label
var _anuncio: Label
var _sub: Label
var _anuncio_t := 0.0
var _anuncio_dur := 1.6
var _choque: Label


class Lienzo extends Control:
	var hud: Hud

	func _draw() -> void:
		hud.dibujar(self)


func preparar(c: Combate) -> void:
	combate = c
	layer = 5
	var raiz := Control.new()
	raiz.set_anchors_preset(Control.PRESET_FULL_RECT)
	raiz.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(raiz)
	var dibujo := Lienzo.new()
	dibujo.hud = self
	dibujo.set_anchors_preset(Control.PRESET_FULL_RECT)
	dibujo.mouse_filter = Control.MOUSE_FILTER_IGNORE
	raiz.add_child(dibujo)
	lienzo = dibujo

	for l: Luchador in combate.luchadores:
		_fantasma[l.lado] = l.vida
		var derecha := l.lado == 1
		var nombre := _etiqueta(raiz, str(l.def["nombre"]).to_upper(), 22, TINTA, 6)
		nombre.position = Vector2(96, 56) if not derecha else Vector2(0, 56)
		if derecha:
			nombre.set_anchors_preset(Control.PRESET_TOP_RIGHT)
			nombre.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
			nombre.offset_left = -560
			nombre.offset_right = -96
			nombre.offset_top = 56
		_nombres.append(nombre)
		var combo := _etiqueta(raiz, "", 44, ORO, 10)
		combo.set_anchors_preset(Control.PRESET_CENTER_RIGHT if derecha else Control.PRESET_CENTER_LEFT)
		combo.offset_top = -120
		if derecha:
			combo.offset_left = -360
			combo.offset_right = -40
			combo.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		else:
			combo.offset_left = 40
			combo.offset_right = 360
		_combos.append(combo)
		var aviso := _etiqueta(raiz, "", 26, Color(0.6, 0.9, 1.0), 8)
		aviso.set_anchors_preset(Control.PRESET_CENTER_RIGHT if derecha else Control.PRESET_CENTER_LEFT)
		aviso.offset_top = -60
		if derecha:
			aviso.offset_left = -360
			aviso.offset_right = -40
			aviso.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		else:
			aviso.offset_left = 40
			aviso.offset_right = 360
		_avisos.append(aviso)

	_tiempo = _etiqueta(raiz, "", 40, TINTA, 10)
	_tiempo.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_tiempo.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_tiempo.offset_left = -60
	_tiempo.offset_right = 60
	_tiempo.offset_top = 18

	_anuncio = _etiqueta(raiz, "", 84, ORO, 16)
	_anuncio.set_anchors_preset(Control.PRESET_CENTER)
	_anuncio.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_anuncio.offset_left = -640
	_anuncio.offset_right = 640
	_anuncio.offset_top = -150
	_anuncio.offset_bottom = -40
	_sub = _etiqueta(raiz, "", 28, TINTA, 8)
	_sub.set_anchors_preset(Control.PRESET_CENTER)
	_sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_sub.offset_left = -640
	_sub.offset_right = 640
	_sub.offset_top = -40
	_sub.offset_bottom = 0

	_choque = _etiqueta(raiz, "¡MACHACA J / X O K / Y!", 26, ORO, 8)
	_choque.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_choque.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_choque.offset_left = -400
	_choque.offset_right = 400
	_choque.offset_top = -170
	_choque.offset_bottom = -130
	_choque.visible = false


func actualizar(dt: float) -> void:
	for l: Luchador in combate.luchadores:
		var f: float = _fantasma[l.lado]
		if f > l.vida:
			f = maxf(l.vida, f - maxf(260.0 * dt, (f - l.vida) * 2.2 * dt))
		else:
			f = l.vida
		_fantasma[l.lado] = f
		var n: int = combate.combos[l.lado]
		_combos[l.lado].text = "%d GOLPES" % n if n >= 2 else ""
		_aviso_t[l.lado] = float(_aviso_t[l.lado]) - dt
		_avisos[l.lado].visible = _aviso_t[l.lado] > 0.0
	_tiempo.text = str(int(ceil(maxf(combate.tiempo, 0.0))))
	_anuncio_t += dt
	var k := clampf(_anuncio_t / _anuncio_dur, 0.0, 1.0)
	var alfa := 1.0 if k < 0.75 else 1.0 - (k - 0.75) / 0.25
	_anuncio.modulate.a = alfa
	_sub.modulate.a = alfa
	var escala := 1.0 + maxf(0.0, 0.35 - _anuncio_t * 2.5)
	_anuncio.pivot_offset = _anuncio.size * 0.5
	_anuncio.scale = Vector2(escala, escala)
	_choque.visible = not combate.choque.is_empty()
	lienzo.queue_redraw()


func anunciar(texto: String, sub := "", color := ORO, duracion := 1.6) -> void:
	_anuncio.text = texto
	_sub.text = sub
	_anuncio.label_settings.font_color = color
	_anuncio_t = 0.0
	_anuncio_dur = duracion
	Sonidos.tocar("anuncio", -6.0)


func aviso(lado: int, texto: String) -> void:
	_avisos[lado].text = texto
	_aviso_t[lado] = 1.0


func dibujar(c: Control) -> void:
	var ancho := c.size.x
	for l: Luchador in combate.luchadores:
		var derecha := l.lado == 1
		var x := ancho - 40.0 - ANCHO_VIDA if derecha else 40.0
		_retrato(c, l, Vector2(x - 6.0 if not derecha else x + ANCHO_VIDA + 6.0, 44.0), derecha)
		_vida(c, l, x + (0.0 if derecha else 48.0) - (48.0 if derecha else 0.0), 26.0, derecha)
		_ki(c, l, x + (0.0 if derecha else 48.0) - (48.0 if derecha else 0.0), 88.0, derecha)
	if not combate.choque.is_empty():
		_medidor_choque(c)


func _retrato(c: Control, l: Luchador, centro: Vector2, derecha: bool) -> void:
	var colores: Dictionary = l.def["colores"]
	var pos := centro + Vector2(-20.0 if derecha else 20.0, 0.0)
	c.draw_circle(pos, 30.0, Color(0.07, 0.05, 0.13))
	c.draw_circle(pos, 26.0, colores["arriba"])
	c.draw_circle(pos + Vector2(0, -4), 14.0, colores["piel"])
	c.draw_arc(pos, 30.0, 0.0, TAU, 40, ORO, 3.0)


func _vida(c: Control, l: Luchador, x: float, y: float, derecha: bool) -> void:
	var tramo := l.vida_max / 3.0
	var ancho_tramo := (ANCHO_VIDA - 48.0 - HUECO * 2.0) / 3.0
	for s in 3:
		# Se vacía desde el centro de la pantalla hacia fuera.
		var orden := 2 - s if derecha else s
		var sx := x + orden * (ancho_tramo + HUECO)
		var caja := Rect2(sx, y, ancho_tramo, ALTO_VIDA)
		c.draw_rect(caja.grow(3.0), FONDO)
		var lleno := clampf((l.vida - s * tramo) / tramo, 0.0, 1.0)
		var fantasma := clampf((float(_fantasma[l.lado]) - s * tramo) / tramo, 0.0, 1.0)
		var color := ORO if l.vida > l.vida_max * 0.3 else Color(1.0, 0.42, 0.3)
		_relleno(c, caja, fantasma, Color(1.0, 0.25, 0.22), derecha)
		_relleno(c, caja, lleno, color, derecha)
		if lleno > 0.0:
			_relleno(c, Rect2(caja.position, Vector2(caja.size.x, 5.0)), lleno, Color(1, 1, 1, 0.45), derecha)


func _ki(c: Control, l: Luchador, x: float, y: float, derecha: bool) -> void:
	var colores: Dictionary = l.def["colores"]
	var ancho_barra := (ANCHO_VIDA - 48.0 - HUECO * 4.0) / 5.0 * 0.62
	for s in 5:
		var orden := s if not derecha else s
		var sx := x + orden * (ancho_barra + HUECO) if not derecha else x + (ANCHO_VIDA - 48.0) - (orden + 1) * (ancho_barra + HUECO)
		var caja := Rect2(sx, y, ancho_barra, 12.0)
		c.draw_rect(caja.grow(2.0), FONDO)
		var lleno := clampf((l.ki - s * Luchador.KI_BARRA) / Luchador.KI_BARRA, 0.0, 1.0)
		var color: Color = colores["ki"] if lleno >= 1.0 else (colores["ki"] as Color).darkened(0.45)
		_relleno(c, caja, lleno, color, derecha)
	if l.ki >= Luchador.COSTE_SUPER:
		var texto_x := x if not derecha else x + ANCHO_VIDA - 48.0 - 120.0
		c.draw_string(ThemeDB.fallback_font, Vector2(texto_x, y + 34.0), "SÚPER LISTO", HORIZONTAL_ALIGNMENT_LEFT, -1, 16, colores["ki_nucleo"])


func _relleno(c: Control, caja: Rect2, k: float, color: Color, desde_derecha: bool) -> void:
	if k <= 0.0:
		return
	var ancho := caja.size.x * k
	var x := caja.position.x + (caja.size.x - ancho if desde_derecha else 0.0)
	c.draw_rect(Rect2(x, caja.position.y, ancho, caja.size.y), color)


func _medidor_choque(c: Control) -> void:
	var a: Rayo = combate.choque["a"]
	var b: Rayo = combate.choque["b"]
	var pos: float = combate.choque["pos"]
	var ancho := 640.0
	var x := (c.size.x - ancho) * 0.5
	var y := c.size.y - 120.0
	var caja := Rect2(x, y, ancho, 26.0)
	c.draw_rect(caja.grow(4.0), FONDO)
	var izquierda := a.dueno if a.dueno.lado == 0 else b.dueno
	var lado_a := pos if izquierda == a.dueno else 1.0 - pos
	c.draw_rect(Rect2(x, y, ancho * lado_a, 26.0), izquierda.def["colores"]["ki"])
	c.draw_rect(Rect2(x + ancho * lado_a, y, ancho * (1.0 - lado_a), 26.0), izquierda.rival.def["colores"]["ki"])
	c.draw_rect(Rect2(x + ancho * lado_a - 4.0, y - 8.0, 8.0, 42.0), Color(1, 1, 1))


func _etiqueta(padre: Control, texto: String, tam: int, color: Color, contorno: int) -> Label:
	var etiqueta := Label.new()
	etiqueta.text = texto
	var ajustes := LabelSettings.new()
	ajustes.font_size = tam
	ajustes.font_color = color
	ajustes.outline_size = contorno
	ajustes.outline_color = Color(0.07, 0.04, 0.12)
	etiqueta.label_settings = ajustes
	etiqueta.mouse_filter = Control.MOUSE_FILTER_IGNORE
	padre.add_child(etiqueta)
	return etiqueta
