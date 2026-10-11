class_name ControlCPU
extends RefCounted

## Rival controlado por la máquina. Rellena la misma Intencion que el jugador, así que
## no hace trampas: tiene que acercarse, gastar ki y reaccionar con retraso como una persona.

const NIVELES := {
	"facil": {"reaccion": 0.42, "guardia": 0.22, "esquiva": 0.06, "agresion": 0.45, "machaque": 4.5, "super": 0.25},
	"normal": {"reaccion": 0.26, "guardia": 0.45, "esquiva": 0.18, "agresion": 0.65, "machaque": 7.0, "super": 0.5},
	"dificil": {"reaccion": 0.14, "guardia": 0.65, "esquiva": 0.38, "agresion": 0.82, "machaque": 9.5, "super": 0.75},
}

var n: Dictionary
var azar := RandomNumberGenerator.new()
var plan := "acercarse"
var plan_t := 0.0
var duracion_plan := 0.0
var lado_rodeo := 1.0
var disparos := 0
var espera_disparo := 0.0
var mantener_golpe := 0.0
var respuesta := ""
var respuesta_t := 0.0
var reaccion_en := -1.0
var amenaza_vista := ""
var machaque := 0.0
var _ultimo_paso_combo := 0
var _seguir_combo := false
var _pulso_hecho := false
var _ki_objetivo := 300.0


func _init(dificultad := "normal", semilla := 1) -> void:
	n = NIVELES.get(dificultad, NIVELES["normal"])
	azar.seed = semilla


func leer(i: Intencion, yo: Luchador, dt: float) -> void:
	i.limpiar()
	var r := yo.rival
	if r == null or yo.combate == null or yo.combate.fase != "pelea":
		return
	plan_t += dt
	match yo.estado:
		Luchador.Estado.CHOQUE:
			machaque += dt * float(n["machaque"]) * azar.randf_range(0.8, 1.2)
			if machaque >= 1.0:
				machaque -= 1.0
				i.golpe_pulsado = true
			return
		Luchador.Estado.GOLPE:
			if yo.paso_combo != _ultimo_paso_combo:
				_ultimo_paso_combo = yo.paso_combo
				_seguir_combo = azar.randf() < 0.5 + 0.45 * float(n["agresion"])
			if _seguir_combo and yo.t > 0.06:
				i.golpe_pulsado = true
			return
		Luchador.Estado.PREPARA_GOLPE:
			mantener_golpe -= dt
			i.golpe = mantener_golpe > 0.0
			return
		Luchador.Estado.CARGANDO_KI:
			i.cargar = yo.ki < _ki_objetivo and _amenaza(yo, r).is_empty()
			return
		Luchador.Estado.GUARDIA:
			respuesta_t -= dt
			i.guardia = respuesta_t > 0.0
			return
		Luchador.Estado.LIBRE:
			_ultimo_paso_combo = 0
			_libre(i, yo, r, dt)


func _libre(i: Intencion, yo: Luchador, r: Luchador, dt: float) -> void:
	var d := yo.distancia()
	var amenaza := _amenaza(yo, r)
	if amenaza != amenaza_vista:
		amenaza_vista = amenaza
		reaccion_en = float(n["reaccion"]) * azar.randf_range(0.7, 1.3) if not amenaza.is_empty() else -1.0
	if reaccion_en >= 0.0:
		reaccion_en -= dt
		if reaccion_en < 0.0 and _reaccionar(i, yo, r, amenaza):
			return

	# Rematar: si el rival sale volando y hay ki, súper.
	if r.estado == Luchador.Estado.LANZADO and yo.ki >= Luchador.COSTE_SUPER and azar.randf() < float(n["super"]) * 0.08:
		i.super_pulsado = true
		return

	if plan_t >= duracion_plan:
		_elegir_plan(yo, r, d)
	_ejecutar_plan(i, yo, r, d, dt)


func _amenaza(yo: Luchador, r: Luchador) -> String:
	var d := yo.distancia()
	if r.estado in [Luchador.Estado.SUPER_CARGA, Luchador.Estado.SUPER_RAYO]:
		return "rayo"
	if r.esta_atacando() and d < 6.0:
		return "cuerpo"
	for b: RafagaKi in yo.combate.rafagas:
		if b.objetivo == yo and not b.terminado and b.global_position.distance_to(yo.global_position) < 14.0:
			return "rafaga"
	return ""


func _reaccionar(i: Intencion, yo: Luchador, r: Luchador, amenaza: String) -> bool:
	match amenaza:
		"cuerpo":
			if yo.ki >= Luchador.COSTE_ESQUIVA and azar.randf() < float(n["esquiva"]):
				i.impulso_pulsado = true
				return true
			if azar.randf() < float(n["guardia"]):
				respuesta_t = 0.6
				i.guardia = true
				return true
		"rafaga":
			if azar.randf() < float(n["guardia"]):
				respuesta_t = 0.35
				i.guardia = true
				return true
			i.impulso_pulsado = true
			i.mover = Vector2(lado_rodeo, 0.0)
			return true
		"rayo":
			if yo.ki >= Luchador.COSTE_SUPER and r.estado == Luchador.Estado.SUPER_CARGA and azar.randf() < float(n["super"]):
				i.super_pulsado = true
				return true
			if yo.ki >= Luchador.COSTE_ESQUIVA and azar.randf() < float(n["esquiva"]) * 2.0:
				i.impulso_pulsado = true
				i.mover = Vector2(lado_rodeo, 0.0)
				return true
			respuesta_t = 1.2
			i.guardia = true
			return true
	return false


func _elegir_plan(yo: Luchador, r: Luchador, d: float) -> void:
	plan_t = 0.0
	duracion_plan = azar.randf_range(0.5, 1.3)
	_pulso_hecho = false
	var agresion: float = n["agresion"]
	var opciones: Dictionary = {}
	if d > 28.0:
		opciones = {"acercarse": 3.0, "disparar": 1.5, "cargar": 2.0 if yo.ki < 300.0 else 0.0}
	elif d > 6.0:
		opciones = {
			"embestir": 2.5 * agresion,
			"disparar": 1.5,
			"rodear": 1.5,
			"acercarse": 1.0,
			"cargar": 1.2 if yo.ki < 150.0 and d > 14.0 else 0.0,
			"super": float(n["super"]) * 1.5 if yo.ki >= Luchador.COSTE_SUPER else 0.0,
		}
	else:
		opciones = {
			"combo": 3.0 * agresion,
			"fuerte": 1.0 * agresion,
			"alejarse": 0.8,
			"rodear": 0.7,
			"guardia": 0.6,
		}
	if r.estado == Luchador.Estado.ATURDIDO and d <= 3.0:
		opciones = {"combo": 1.0}
	plan = _sortear(opciones)
	match plan:
		"disparar":
			disparos = azar.randi_range(2, 4)
			espera_disparo = 0.0
		"cargar":
			_ki_objetivo = azar.randf_range(250.0, 450.0)
		"rodear":
			if azar.randf() < 0.5:
				lado_rodeo = -lado_rodeo
		"guardia":
			respuesta_t = 0.5


func _ejecutar_plan(i: Intencion, yo: Luchador, r: Luchador, d: float, dt: float) -> void:
	var diferencia_altura := r.global_position.y - yo.global_position.y
	i.altura = clampf(diferencia_altura / 3.0, -1.0, 1.0)
	match plan:
		"acercarse":
			i.mover = Vector2(0.0, 1.0)
			i.impulso = d > 14.0
		"rodear":
			i.mover = Vector2(lado_rodeo, 0.35 if d > 12.0 else -0.2)
			if azar.randf() < 0.01:
				i.ki_pulsado = true
		"alejarse":
			i.mover = Vector2(lado_rodeo * 0.4, -1.0)
			if not _pulso_hecho:
				_pulso_hecho = true
				i.impulso_pulsado = true
		"disparar":
			i.mover = Vector2(lado_rodeo * 0.6, 0.0)
			espera_disparo -= dt
			if disparos > 0 and espera_disparo <= 0.0 and yo.ki >= Luchador.COSTE_RAFAGA:
				i.ki_pulsado = true
				disparos -= 1
				espera_disparo = azar.randf_range(0.2, 0.35)
		"cargar":
			if yo.ki < _ki_objetivo:
				i.cargar = true
		"embestir", "combo":
			if not _pulso_hecho:
				_pulso_hecho = true
				i.golpe_pulsado = true
				mantener_golpe = 0.0
			else:
				i.mover = Vector2(0.0, 1.0)
		"fuerte":
			if not _pulso_hecho:
				_pulso_hecho = true
				i.golpe_pulsado = true
				i.golpe = true
				mantener_golpe = azar.randf_range(0.4, 0.9)
		"super":
			if not _pulso_hecho:
				_pulso_hecho = true
				i.super_pulsado = true
		"guardia":
			respuesta_t -= dt
			i.guardia = respuesta_t > 0.0


func _sortear(opciones: Dictionary) -> String:
	var total := 0.0
	for peso: float in opciones.values():
		total += maxf(peso, 0.0)
	if total <= 0.0:
		return "rodear"
	var tirada := azar.randf() * total
	for clave: String in opciones:
		tirada -= maxf(float(opciones[clave]), 0.0)
		if tirada <= 0.0:
			return clave
	return opciones.keys()[0]
