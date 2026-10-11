class_name Combate
extends Node3D

## Un combate completo: arena, dos luchadores, proyectiles, rayos, choque de rayos,
## cámara, interfaz y fases (presentación, pelea, K.O., fin).
## Todo avanza en paso(dt); _physics_process solo lo llama a 60 fotogramas por segundo.

signal terminado(ganador: Luchador)

const DURACION_PRESENTACION := 2.4
const DURACION_KO := 3.2

var arena: Arena
var efectos: Efectos
var camara: CamaraCombate
var hud: Hud
var luchadores: Array[Luchador] = []
var rafagas: Array[RafagaKi] = []
var rayos: Array[Rayo] = []
var choque: Dictionary = {}

var fase := "presentacion"  # presentacion, pelea, ko, fin
var fase_t := 0.0
var tiempo := 150.0
var parada := 0.0
var pausado := false
var demo := false
var ganador: Luchador = null
var resultado := ""  # ko, tiempo, empate
var ultimo_anuncio := ""
var combos := [0, 0]
var combo_t := [0.0, 0.0]

var _terminado_emitido := false
var _victoria_puesta := false
var _chispas_choque := 0.0


func preparar(id_a: String, id_b: String, control_a: Variant, control_b: Variant, opciones := {}) -> void:
	demo = opciones.get("demo", false)
	arena = Arena.new()
	arena.name = "Arena"
	add_child(arena)
	arena.construir(opciones.get("semilla", 7), opciones.get("sombras", true))
	efectos = Efectos.new()
	efectos.name = "Efectos"
	add_child(efectos)

	var a := Luchador.new()
	add_child(a)
	a.preparar(Personajes.datos(id_a), 0, self)
	var b := Luchador.new()
	add_child(b)
	b.preparar(Personajes.datos(id_b), 1, self)
	a.rival = b
	b.rival = a
	a.control = control_a
	b.control = control_b
	a.global_position = Vector3(0, 6, 9)
	b.global_position = Vector3(0, 6, -9)
	a.mirar_al_rival()
	b.mirar_al_rival()
	luchadores.clear()
	luchadores.append(a)
	luchadores.append(b)
	tiempo = opciones.get("tiempo", 150.0)

	if opciones.get("camara", true):
		camara = CamaraCombate.new()
		camara.name = "Camara"
		add_child(camara)
		camara.preparar(a, b)
		camara.make_current()
		efectos.temblor.connect(camara.temblar)
	if opciones.get("hud", true):
		hud = Hud.new()
		add_child(hud)
		hud.preparar(self)

	if opciones.get("sin_presentacion", false):
		_empezar_pelea()
	else:
		fase = "presentacion"
		fase_t = 0.0
		anuncio("RYŪSEI CLASH", "%s  contra  %s" % [a.def["nombre"], b.def["nombre"]])
		if not demo:
			Sonidos.voz(a.id, "entrada")


func _physics_process(delta: float) -> void:
	if not pausado:
		paso(delta)


func paso(dt: float) -> void:
	fase_t += dt
	if efectos != null:
		efectos.paso(dt)
	if camara != null:
		camara.paso(dt)
	if hud != null:
		hud.actualizar(dt)
	if parada > 0.0:
		parada -= dt
		return

	var escala := 1.0
	match fase:
		"presentacion":
			if fase_t >= DURACION_PRESENTACION:
				_empezar_pelea()
		"pelea":
			tiempo -= dt
			if tiempo <= 0.0:
				tiempo = 0.0
				_fin_por_tiempo()
		"ko":
			if fase_t < 1.1:
				escala = 0.35  # cámara lenta en el K.O.
			if fase_t >= 1.3 and not _victoria_puesta:
				_poner_victoria()
			if fase_t >= DURACION_KO:
				_terminar()
	var d := dt * escala
	for l: Luchador in luchadores:
		l.paso(d)
	_paso_rafagas(d)
	_paso_rayos(d)
	_paso_choque(d)
	for i in 2:
		combo_t[i] = float(combo_t[i]) - dt
		if combo_t[i] <= 0.0:
			combos[i] = 0
	_sonidos_continuos()


func anuncio(texto: String, sub := "", color := Color(1.0, 0.82, 0.25)) -> void:
	ultimo_anuncio = texto
	if hud != null:
		hud.anunciar(texto, sub, color)


# --- creación de proyectiles ------------------------------------------------------------------

func crear_rafaga(l: Luchador, desde: Vector3) -> RafagaKi:
	var r := RafagaKi.new()
	add_child(r)
	r.preparar(l, desde)
	rafagas.append(r)
	Sonidos.tocar("rafaga", -6.0, randf_range(0.95, 1.1))
	return r


func crear_rayo(l: Luchador) -> Rayo:
	var r := Rayo.new()
	add_child(r)
	r.preparar(l, self)
	rayos.append(r)
	Sonidos.tocar("explosion", -8.0, 1.4)
	return r


# --- avisos de los luchadores ------------------------------------------------------------------

func al_impactar(atacante: Luchador, victima: Luchador, info: Dictionary, resultado_golpe: String) -> void:
	var punto := victima.global_position.lerp(atacante.global_position, 0.35) + Vector3.UP * 0.3
	var fuerte: bool = info.get("fuerte", false)
	var colores: Dictionary = atacante.def["colores"]
	match resultado_golpe:
		"golpeado":
			efectos.chispas(punto, colores["ki_nucleo"], 16 if fuerte else 10, 12.0 if fuerte else 8.0)
			efectos.destello(punto, Color(1, 1, 1), 1.7 if fuerte else 0.9)
			if fuerte:
				efectos.onda(punto, colores["ki"], 4.0, 0.35, atacante.hacia_rival())
				efectos.temblor.emit(0.6)
				parada = 0.11
				Sonidos.tocar("golpe_fuerte", 0.0, randf_range(0.92, 1.05))
			else:
				efectos.temblor.emit(0.15)
				parada = 0.05
				Sonidos.tocar("golpe", -2.0, randf_range(0.9, 1.12))
			combos[atacante.lado] = int(combos[atacante.lado]) + 1
			combo_t[atacante.lado] = 1.2
		"bloqueado":
			efectos.chispas(punto, Color(0.7, 0.9, 1.0), 8, 6.0)
			efectos.destello(punto, Color(0.6, 0.85, 1.0), 0.7)
			parada = 0.035
			Sonidos.tocar("bloqueo", -3.0, randf_range(0.95, 1.05))
		"guardia_rota":
			efectos.onda(punto, Color(0.7, 0.9, 1.0), 4.5, 0.4, atacante.hacia_rival())
			efectos.destello(punto, Color(1, 1, 1), 1.8)
			efectos.temblor.emit(0.5)
			parada = 0.12
			Sonidos.tocar("golpe_fuerte")
			if hud != null:
				hud.aviso(victima.lado, "¡GUARDIA ROTA!")


func al_recibir_dano(_victima: Luchador, _atacante: Luchador, _cantidad: float) -> void:
	pass


func al_esquivar(l: Luchador, desde: Vector3, hasta: Vector3) -> void:
	var colores: Dictionary = l.def["colores"]
	efectos.estela(desde, colores["ki"])
	efectos.destello(hasta, colores["ki_nucleo"], 1.2)
	Sonidos.tocar("teletransporte", -2.0)
	if hud != null:
		hud.aviso(l.lado, "¡ESQUIVA!")


func al_empezar_super(l: Luchador) -> void:
	var colores: Dictionary = l.def["colores"]
	Sonidos.tocar("super", -2.0)
	Sonidos.voz(l.id, "tecnica")
	efectos.onda(l.global_position, colores["ki"], 5.0, 0.5)
	if camara != null and camara.objetivo == l:
		camara.enfocar(l, Luchador.TIEMPO_SUPER_CARGA)
	var tecnica: Dictionary = l.def.get("super", {})
	anuncio(str(tecnica.get("nombre", "SÚPER")).to_upper(), l.def["nombre"], colores["ki"])


func al_alcanzar_rayo(rayo: Rayo) -> void:
	efectos.onda(rayo.cabeza, rayo.color, 5.0, 0.45, rayo.direccion)
	efectos.temblor.emit(0.55)
	Sonidos.tocar("explosion", -2.0)


func al_ko(l: Luchador) -> void:
	if fase != "pelea":
		return
	fase = "ko"
	fase_t = 0.0
	resultado = "ko"
	ganador = l.rival
	anuncio("K.O.", "", Color(1.0, 0.35, 0.25))
	Sonidos.tocar("ko")
	efectos.temblor.emit(1.0)
	efectos.destello(l.global_position, Color(1, 1, 1), 4.0, 0.4)


func explosion(pos: Vector3, color: Color, tam := 1.0) -> void:
	efectos.destello(pos, color, tam * 2.5, 0.4)
	efectos.destello(pos, Color(1, 1, 1), tam * 1.2, 0.2)
	efectos.onda(pos, color, tam * 5.0, 0.5)
	efectos.chispas(pos, color, 24, 16.0)
	efectos.temblor.emit(0.45)
	Sonidos.tocar("explosion", -2.0, randf_range(0.9, 1.1))


func impacto_suelo(l: Luchador, punto: Vector3, fuerza: float) -> void:
	efectos.onda(punto + Vector3.UP * 0.1, Color(1.0, 0.95, 0.85), 3.0 + fuerza * 0.12, 0.5)
	efectos.escombros(punto, Color(0.62, 0.5, 0.38), 14)
	efectos.temblor.emit(0.35)
	Sonidos.tocar("impacto")
	_dano_ambiente(l, 25.0)


func impacto_roca(l: Luchador, roca: Dictionary, pos: Vector3) -> void:
	arena.romper(roca)
	efectos.escombros(pos, Color(0.72, 0.56, 0.42), 26)
	efectos.onda(pos, Color(1.0, 0.92, 0.8), 6.0, 0.5, l.vel)
	efectos.temblor.emit(0.75)
	Sonidos.tocar("explosion")
	_dano_ambiente(l, 40.0)


func _dano_ambiente(l: Luchador, cantidad: float) -> void:
	if l.estado == Luchador.Estado.KO or fase != "pelea":
		return
	l.vida = maxf(l.vida - cantidad, 1.0)


# --- proyectiles y rayos ---------------------------------------------------------------------

func _paso_rafagas(dt: float) -> void:
	for r: RafagaKi in rafagas.duplicate():
		if r.terminado:
			_quitar_rafaga(r)
			continue
		r.paso(dt)
		if r.terminado:
			continue
		var objetivo := r.objetivo
		if objetivo.estado != Luchador.Estado.KO and r.global_position.distance_to(objetivo.global_position) < Luchador.RADIO + 0.4:
			var info := {"dano": r.dano, "aturdido": 0.22, "empuje": 2.5, "cuerpo": false}
			var res := objetivo.recibir_golpe(r.dueno, info)
			if res != "ignorado" and res != "esquivado":
				al_impactar(r.dueno, objetivo, info, res)
				efectos.destello(r.global_position, r.dueno.def["colores"]["ki"], 1.3)
				r.terminar()
				continue
		for otra: RafagaKi in rafagas:
			if otra != r and not otra.terminado and otra.dueno != r.dueno and r.global_position.distance_to(otra.global_position) < 0.8:
				explosion(r.global_position, r.dueno.def["colores"]["ki"], 0.5)
				r.terminar()
				otra.terminar()
				break
		if r.terminado:
			continue
		if r.global_position.y < arena.altura_suelo(r.global_position) + 0.2:
			explosion(r.global_position, r.dueno.def["colores"]["ki"], 0.6)
			r.terminar()
			continue
		var roca: Variant = arena.roca_en(r.global_position, 0.3)
		if roca != null:
			arena.danar(roca, 25.0)
			explosion(r.global_position, r.dueno.def["colores"]["ki"], 0.6)
			r.terminar()


func _quitar_rafaga(r: RafagaKi) -> void:
	rafagas.erase(r)
	r.queue_free()


func _paso_rayos(dt: float) -> void:
	for r: Rayo in rayos.duplicate():
		r.paso(dt)
		if r.terminado and not r.visible:
			rayos.erase(r)
			r.queue_free()
	if choque.is_empty():
		_detectar_choque()


func _detectar_choque() -> void:
	var activos: Array[Rayo] = []
	for r: Rayo in rayos:
		if not r.terminado and r.impactando < 0.0 and not r.en_choque:
			activos.append(r)
	if activos.size() < 2:
		return
	var a := activos[0]
	var b := activos[1]
	if a.dueno == b.dueno:
		return
	var d := b.cabeza - a.cabeza
	var hacia_delante := d.dot(a.direccion)
	var lateral := (d - a.direccion * hacia_delante).length()
	if (hacia_delante < 0.0 or d.length() < 3.0) and lateral < 3.5:
		_empezar_choque(a, b)


func _empezar_choque(a: Rayo, b: Rayo) -> void:
	var la := a.dueno
	var lb := b.dueno
	var punto := (a.cabeza + b.cabeza) * 0.5
	var total := maxf(la.global_position.distance_to(lb.global_position), 0.1)
	var pos := clampf(la.global_position.distance_to(punto) / total, 0.2, 0.8)
	choque = {"a": a, "b": b, "pos": pos, "t": 0.0, "fuerza_a": 0.0, "fuerza_b": 0.0}
	a.en_choque = true
	b.en_choque = true
	la.cambiar(Luchador.Estado.CHOQUE)
	lb.cambiar(Luchador.Estado.CHOQUE)
	explosion(punto, Color(1, 1, 1), 1.2)
	anuncio("¡CHOQUE DE RAYOS!", "Machaca golpe o ki para empujar", Color(1.0, 0.9, 0.4))


func _paso_choque(dt: float) -> void:
	if choque.is_empty():
		return
	var a: Rayo = choque["a"]
	var b: Rayo = choque["b"]
	if a.terminado or b.terminado:
		var queda := b if a.terminado else a
		var perdido := a if a.terminado else b
		_resolver_choque(queda, perdido)
		return
	var la := a.dueno
	var lb := b.dueno
	choque["t"] = float(choque["t"]) + dt
	var pulsa_a := 1.0 if (la.intencion.golpe_pulsado or la.intencion.ki_pulsado) else 0.0
	var pulsa_b := 1.0 if (lb.intencion.golpe_pulsado or lb.intencion.ki_pulsado) else 0.0
	choque["fuerza_a"] = float(choque["fuerza_a"]) * exp(-2.5 * dt) + pulsa_a
	choque["fuerza_b"] = float(choque["fuerza_b"]) * exp(-2.5 * dt) + pulsa_b
	var balance := clampf(float(choque["fuerza_a"]) - float(choque["fuerza_b"]), -4.0, 4.0)
	choque["pos"] = clampf(float(choque["pos"]) + balance * 0.12 * dt, 0.0, 1.0)
	var punto := la.global_position.lerp(lb.global_position, choque["pos"])
	a.cabeza = punto
	b.cabeza = punto
	_chispas_choque -= dt
	if _chispas_choque <= 0.0:
		_chispas_choque = 0.06
		efectos.chispas(punto, Color(1.0, 0.95, 0.7), 10, 14.0)
		efectos.temblor.emit(0.25)
	var pos: float = choque["pos"]
	var t: float = choque["t"]
	if pos >= 0.9 or (t >= 6.0 and pos > 0.5):
		_resolver_choque(a, b)
	elif pos <= 0.1 or (t >= 6.0 and pos <= 0.5):
		_resolver_choque(b, a)


func _resolver_choque(gana: Rayo, pierde: Rayo) -> void:
	choque = {}
	var punto := pierde.dueno.global_position
	pierde.terminar()
	if pierde.dueno.estado == Luchador.Estado.CHOQUE:
		pierde.dueno.cambiar(Luchador.Estado.ATURDIDO)
		pierde.dueno.duracion_aturdido = 0.6
	if not gana.terminado:
		gana.en_choque = false
		gana.multiplicador = 1.3
		gana.cabeza = punto
		gana.impactando = 0.0
		if gana.dueno.estado == Luchador.Estado.CHOQUE:
			gana.dueno.cambiar(Luchador.Estado.SUPER_RAYO)
	explosion(punto, gana.color, 1.6)
	anuncio("¡%s GANA EL CHOQUE!" % str(gana.dueno.def["nombre"]).to_upper(), "", gana.color)


# --- fases ------------------------------------------------------------------------------------

func _empezar_pelea() -> void:
	fase = "pelea"
	fase_t = 0.0
	for l: Luchador in luchadores:
		if l.estado == Luchador.Estado.PRESENTACION:
			l.cambiar(Luchador.Estado.LIBRE)
	anuncio("¡PELEA!", "", Color(1.0, 0.82, 0.25))
	Sonidos.tocar("anuncio")


func _fin_por_tiempo() -> void:
	if fase != "pelea":
		return
	fase = "ko"
	fase_t = 0.0
	var a := luchadores[0]
	var b := luchadores[1]
	var pa := a.vida / a.vida_max
	var pb := b.vida / b.vida_max
	if is_equal_approx(pa, pb):
		ganador = null
		resultado = "empate"
		anuncio("¡TIEMPO!", "Empate")
	else:
		ganador = a if pa > pb else b
		resultado = "tiempo"
		anuncio("¡TIEMPO!", "Gana %s" % ganador.def["nombre"])
	Sonidos.tocar("anuncio")


func _poner_victoria() -> void:
	_victoria_puesta = true
	if ganador != null and ganador.estado != Luchador.Estado.KO:
		for r: Rayo in rayos:
			r.terminar()
		ganador.cambiar(Luchador.Estado.VICTORIA)
		if not demo:
			Sonidos.voz(ganador.id, "victoria")


func _terminar() -> void:
	if _terminado_emitido:
		return
	_terminado_emitido = true
	fase = "fin"
	Sonidos.parar_todo()
	terminado.emit(ganador)


func _sonidos_continuos() -> void:
	for l: Luchador in luchadores:
		var cargando := l.estado == Luchador.Estado.CARGANDO_KI or l.estado == Luchador.Estado.SUPER_CARGA
		Sonidos.bucle("carga%d" % l.lado, "carga", cargando, -6.0)
	var hay_rayo := false
	for r: Rayo in rayos:
		if not r.terminado:
			hay_rayo = true
	Sonidos.bucle("rayo", "rayo", hay_rayo and choque.is_empty(), -4.0)
	Sonidos.bucle("choque", "choque", not choque.is_empty(), -2.0)
