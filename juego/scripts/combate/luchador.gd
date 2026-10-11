class_name Luchador
extends Node3D

## Un luchador: estados, movimiento y ataques.
## Toda la lógica avanza en paso(dt), sin la física del motor, para que las pruebas puedan
## simular combates enteros sin ventana y siempre con el mismo resultado.

enum Estado {
	PRESENTACION, LIBRE, EMBESTIDA, PREPARA_GOLPE, GOLPE, GOLPE_FUERTE, RAFAGA,
	CARGANDO_KI, GUARDIA, PASO, SUPER_CARGA, SUPER_RAYO, CHOQUE, ATURDIDO,
	LANZADO, RECUPERACION, KO, VICTORIA,
}

const ALTURA_PIES := 1.02  # distancia de la pelvis (origen) a los pies
const RADIO := 0.55
const ALCANCE := 2.2
const VEL_EMBESTIDA := 30.0
const KI_MAX := 500.0
const KI_BARRA := 100.0
const COSTE_RAFAGA := 12.0
const COSTE_ESQUIVA := 50.0
const COSTE_SUPER := 200.0
const DANO_COMBO := [55.0, 55.0, 65.0, 70.0, 120.0]
const TIEMPO_GOLPE_INICIO := 0.07
const TIEMPO_GOLPE_ACTIVO := 0.05
const TIEMPO_GOLPE_FIN := 0.22
const TIEMPO_CARGA_GOLPE := 0.22
const TIEMPO_FUERTE_INICIO := 0.12
const TIEMPO_SUPER_CARGA := 0.75
const VENTANA_ESQUIVA := 0.22

var def: Dictionary = {}
var id := ""
var lado := 0
var rival: Luchador
var combate: Combate
var control: Variant = null  # ControlJugador, ControlCPU o ControlGuion
var intencion := Intencion.new()
var cuerpo: CuerpoAnime

var vida := 3000.0
var vida_max := 3000.0
var ki := 200.0
var estado: Estado = Estado.PRESENTACION
var t := 0.0
var vel := Vector3.ZERO

var corriendo := false
var paso_combo := 0
var encadenar := false
var golpe_resuelto := false
var carga := 0.0
var duracion_aturdido := 0.0
var invulnerable := 0.0
var espera_rafaga := 0.0
var espera_paso := 0.0
var golpes_recibidos := 0
var mano_rafaga := 0
var paso_dir := Vector3.ZERO
var giro_lanzado := 0.0
var rayo: Rayo = null
var ultimo_resultado := ""
var golpes_conectados := 0


func preparar(datos: Dictionary, numero_lado: int, el_combate: Combate) -> void:
	def = datos
	id = datos["id"]
	lado = numero_lado
	combate = el_combate
	vida_max = datos.get("vida", 3000.0)
	vida = vida_max
	name = "Luchador%d_%s" % [lado + 1, id]
	cuerpo = CuerpoAnime.new()
	cuerpo.name = "Cuerpo"
	add_child(cuerpo)
	cuerpo.construir(datos)
	var modelo := Recursos.modelo(id) if is_instance_valid(Recursos) else null
	if modelo != null:
		cuerpo.usar_modelo(modelo)


func paso(dt: float) -> void:
	t += dt
	invulnerable = maxf(invulnerable - dt, 0.0)
	espera_rafaga = maxf(espera_rafaga - dt, 0.0)
	espera_paso = maxf(espera_paso - dt, 0.0)
	corriendo = false
	if control != null:
		control.leer(intencion, self, dt)
	match estado:
		Estado.PRESENTACION:
			_frenar(dt, 6.0)
		Estado.LIBRE:
			_libre(dt)
		Estado.EMBESTIDA:
			_embestida(dt)
		Estado.PREPARA_GOLPE:
			_prepara_golpe(dt)
		Estado.GOLPE:
			_golpe(dt)
		Estado.GOLPE_FUERTE:
			_golpe_fuerte(dt)
		Estado.RAFAGA:
			_volar(dt, 0.5)
			if t >= 0.14:
				cambiar(Estado.LIBRE)
		Estado.CARGANDO_KI:
			_cargando(dt)
		Estado.GUARDIA:
			_frenar(dt, 8.0)
			if not intencion.guardia and t >= 0.1:
				cambiar(Estado.LIBRE)
		Estado.PASO:
			vel = vel.lerp(paso_dir * 6.0, 1.0 - exp(-9.0 * dt))
			if t >= 0.3:
				cambiar(Estado.LIBRE)
		Estado.SUPER_CARGA:
			_frenar(dt, 10.0)
			if t >= TIEMPO_SUPER_CARGA:
				cambiar(Estado.SUPER_RAYO)
				rayo = combate.crear_rayo(self)
		Estado.SUPER_RAYO:
			_frenar(dt, 12.0)
			if rayo == null or not is_instance_valid(rayo) or rayo.terminado:
				rayo = null
				if t >= 0.3:
					cambiar(Estado.LIBRE)
		Estado.CHOQUE:
			_frenar(dt, 10.0)
		Estado.ATURDIDO:
			_frenar(dt, 5.0)
			if t >= duracion_aturdido:
				cambiar(Estado.LIBRE)
		Estado.LANZADO:
			_lanzado(dt)
		Estado.RECUPERACION:
			_frenar(dt, 6.0)
			if t >= 0.3:
				cambiar(Estado.LIBRE)
		Estado.KO:
			vel.y -= 22.0 * dt
			vel.x *= exp(-1.5 * dt)
			vel.z *= exp(-1.5 * dt)
		Estado.VICTORIA:
			_frenar(dt, 4.0)
	_mover(dt)
	_orientar(dt)
	if cuerpo != null:
		cuerpo.actualizar(dt, self)


func cambiar(nuevo: Estado) -> void:
	estado = nuevo
	t = 0.0
	if nuevo == Estado.LIBRE:
		golpes_recibidos = 0
		paso_combo = 0


# --- consultas ------------------------------------------------------------------------------

func adelante() -> Vector3:
	var d := rival.global_position - global_position
	d.y = 0.0
	if d.length_squared() < 0.0001:
		var frente := -global_transform.basis.z
		frente.y = 0.0
		return frente.normalized() if frente.length_squared() > 0.0001 else Vector3.FORWARD
	return d.normalized()


func hacia_rival() -> Vector3:
	var d := rival.global_position - global_position
	return d.normalized() if d.length_squared() > 0.0001 else adelante()


func distancia() -> float:
	return global_position.distance_to(rival.global_position)


func en_suelo() -> bool:
	return global_position.y <= _suelo() + 0.02


func barras_ki() -> int:
	return int(ki / KI_BARRA)


func posicion_disparo() -> Vector3:
	if cuerpo != null:
		return cuerpo.posicion_manos() + hacia_rival() * 0.3
	return global_position + hacia_rival() * 0.7 + Vector3.UP * 0.35


func esta_atacando() -> bool:
	return estado in [Estado.EMBESTIDA, Estado.GOLPE, Estado.GOLPE_FUERTE, Estado.PREPARA_GOLPE]


# --- estados --------------------------------------------------------------------------------

func _libre(dt: float) -> void:
	var i := intencion
	if i.super_pulsado and ki >= COSTE_SUPER:
		_empezar_super()
		return
	if i.golpe_pulsado:
		if distancia() > ALCANCE + 0.4:
			cambiar(Estado.EMBESTIDA)
			Sonidos.tocar("paso", -2.0, 0.8)
		else:
			cambiar(Estado.PREPARA_GOLPE)
		return
	if i.ki_pulsado and espera_rafaga <= 0.0 and ki >= COSTE_RAFAGA:
		_disparar()
		return
	if i.impulso_pulsado and espera_paso <= 0.0:
		_empezar_paso()
		return
	if i.guardia:
		cambiar(Estado.GUARDIA)
		return
	if i.cargar and ki < KI_MAX:
		cambiar(Estado.CARGANDO_KI)
		return
	_volar(dt, 1.0)


func _volar(dt: float, factor: float) -> void:
	var i := intencion
	var f := adelante()
	var r := f.cross(Vector3.UP)
	var velocidad: float = def.get("velocidad", 15.0) * factor
	corriendo = i.impulso and i.mover.length() > 0.3 and ki > 1.0 and factor >= 1.0
	if corriendo:
		velocidad *= 2.0
		ki = maxf(ki - 18.0 * dt, 0.0)
	var deseada := (f * i.mover.y + r * i.mover.x) * velocidad
	deseada.y = i.altura * velocidad * 0.7
	if distancia() < 1.6 and deseada.dot(f) > 0.0:
		deseada -= f * deseada.dot(f)
	vel = vel.lerp(deseada, 1.0 - exp(-7.0 * dt))


func _frenar(dt: float, rapidez: float) -> void:
	vel = vel.lerp(Vector3.ZERO, 1.0 - exp(-rapidez * dt))


func _embestida(dt: float) -> void:
	var d := rival.global_position - global_position
	if d.length() <= ALCANCE - 0.3:
		_iniciar_golpe(1)
		return
	vel = d.normalized() * VEL_EMBESTIDA
	if t >= 0.9:
		cambiar(Estado.LIBRE)


func _prepara_golpe(dt: float) -> void:
	_frenar(dt, 10.0)
	if not intencion.golpe:
		if t < TIEMPO_CARGA_GOLPE:
			_iniciar_golpe(1)
		else:
			_soltar_fuerte()
		return
	if t >= TIEMPO_CARGA_GOLPE:
		carga = clampf((t - TIEMPO_CARGA_GOLPE) / 0.8, 0.0, 1.0)
	if t >= TIEMPO_CARGA_GOLPE + 0.8:
		_soltar_fuerte()


func _iniciar_golpe(n: int) -> void:
	paso_combo = n
	encadenar = false
	golpe_resuelto = false
	estado = Estado.GOLPE
	t = 0.0


func _golpe(dt: float) -> void:
	if intencion.golpe_pulsado and paso_combo < 5:
		encadenar = true
	var avance := 7.0 if distancia() > 1.5 else 0.0
	vel = vel.lerp(hacia_rival() * avance, 1.0 - exp(-12.0 * dt))
	if not golpe_resuelto and t >= TIEMPO_GOLPE_INICIO:
		golpe_resuelto = true
		Sonidos.tocar("aire", -4.0, 0.9 + 0.08 * paso_combo)
		var ultimo := paso_combo >= 5
		_conectar({
			"dano": DANO_COMBO[paso_combo - 1] * float(def.get("fuerza", 1.0)),
			"aturdido": 0.5,
			"empuje": 3.0,
			"lanza": ultimo,
			"fuerza_lanzado": 26.0,
			"cuerpo": true,
			"fuerte": ultimo,
		})
	var fin_activo := TIEMPO_GOLPE_INICIO + TIEMPO_GOLPE_ACTIVO
	if t >= fin_activo and encadenar and paso_combo < 5 and ultimo_resultado != "fallo":
		_iniciar_golpe(paso_combo + 1)
		return
	if t >= fin_activo + TIEMPO_GOLPE_FIN:
		cambiar(Estado.LIBRE)


func _soltar_fuerte() -> void:
	cambiar(Estado.GOLPE_FUERTE)
	golpe_resuelto = false


func _golpe_fuerte(dt: float) -> void:
	var avance := 9.0 if distancia() > 1.5 else 0.0
	vel = vel.lerp(hacia_rival() * avance, 1.0 - exp(-12.0 * dt))
	if not golpe_resuelto and t >= TIEMPO_FUERTE_INICIO:
		golpe_resuelto = true
		Sonidos.tocar("aire", -2.0, 0.7)
		_conectar({
			"dano": (140.0 + 120.0 * carga) * float(def.get("fuerza", 1.0)),
			"empuje": 6.0,
			"lanza": true,
			"fuerza_lanzado": 28.0 + 18.0 * carga,
			"rompe_guardia": true,
			"cuerpo": true,
			"fuerte": true,
		})
	if t >= TIEMPO_FUERTE_INICIO + 0.4:
		carga = 0.0
		cambiar(Estado.LIBRE)


func _disparar() -> void:
	ki -= COSTE_RAFAGA
	espera_rafaga = 0.16
	cambiar(Estado.RAFAGA)
	mano_rafaga = 1 - mano_rafaga
	var desde := cuerpo.posicion_mano(mano_rafaga == 0) if cuerpo != null else posicion_disparo()
	combate.crear_rafaga(self, desde + hacia_rival() * 0.35)


func _cargando(dt: float) -> void:
	_frenar(dt, 6.0)
	ki = minf(ki + 115.0 * dt, KI_MAX)
	if not intencion.cargar or ki >= KI_MAX:
		cambiar(Estado.LIBRE)


func _empezar_paso() -> void:
	var i := intencion
	var f := adelante()
	var r := f.cross(Vector3.UP)
	var dir := f * i.mover.y + r * i.mover.x + Vector3.UP * i.altura * 0.6
	if dir.length() < 0.2:
		dir = r * (1.0 if lado == 0 else -1.0)
	paso_dir = dir.normalized()
	cambiar(Estado.PASO)
	invulnerable = VENTANA_ESQUIVA
	espera_paso = 0.45
	vel = paso_dir * 26.0
	Sonidos.tocar("paso", -3.0)


func _empezar_super() -> void:
	ki -= COSTE_SUPER
	cambiar(Estado.SUPER_CARGA)
	invulnerable = 0.3
	vel = Vector3.ZERO
	combate.al_empezar_super(self)


func _lanzado(dt: float) -> void:
	vel *= exp(-1.6 * dt)
	vel.y -= 6.0 * dt
	giro_lanzado += dt * 9.0
	if (t >= 0.85 and vel.length() < 9.0) or t >= 1.4:
		cambiar(Estado.RECUPERACION)
		invulnerable = 0.35
		giro_lanzado = 0.0


# --- recibir --------------------------------------------------------------------------------

## Devuelve "golpeado", "bloqueado", "guardia_rota", "esquivado" o "ignorado".
func recibir_golpe(atacante: Luchador, info: Dictionary) -> String:
	if estado == Estado.KO or estado == Estado.VICTORIA:
		return "ignorado"
	if invulnerable > 0.0:
		if estado == Estado.PASO and info.get("cuerpo", false) and ki >= COSTE_ESQUIVA:
			_contraataque(atacante)
			return "esquivado"
		return "ignorado"
	var dir := global_position - atacante.global_position
	dir = dir.normalized() if dir.length_squared() > 0.0001 else -adelante()
	var dano: float = info.get("dano", 0.0)
	var defensa: float = def.get("defensa", 1.0)
	if estado == Estado.GUARDIA and (-global_transform.basis.z).dot(-dir) > -0.2:
		if info.get("rompe_guardia", false):
			_recibir_dano(dano * 0.3 / defensa, atacante)
			duracion_aturdido = 1.1
			cambiar(Estado.ATURDIDO)
			vel = dir * 6.0
			return "guardia_rota"
		_recibir_dano(dano * 0.12 / defensa, atacante)
		vel = dir * float(info.get("empuje", 3.0)) * 0.6
		t = 0.0
		ki = minf(ki + 3.0, KI_MAX)
		return "bloqueado"
	golpes_recibidos += 1
	var escala := maxf(0.45, 1.0 - 0.07 * (golpes_recibidos - 1))
	_recibir_dano(dano * escala / defensa, atacante)
	ki = minf(ki + 6.0, KI_MAX)
	_cortar_rayo()
	if vida <= 0.0:
		_caer_ko(dir)
		return "golpeado"
	if info.get("lanza", false):
		_lanzar(dir * float(info.get("fuerza_lanzado", 24.0)) + Vector3.UP * 4.0)
	else:
		duracion_aturdido = info.get("aturdido", 0.45)
		cambiar(Estado.ATURDIDO)
		vel = dir * float(info.get("empuje", 3.0))
	return "golpeado"


## Daño del rayo, fotograma a fotograma. Devuelve true si este fotograma ha bloqueado.
func recibir_rayo(rayo_rival: Rayo, cantidad: float) -> bool:
	if estado == Estado.KO:
		return false
	var bloquea := estado == Estado.GUARDIA
	_recibir_dano(cantidad * (0.35 if bloquea else 1.0) / float(def.get("defensa", 1.0)), rayo_rival.dueno)
	if not bloquea and estado != Estado.ATURDIDO and estado != Estado.KO:
		_cortar_rayo()
		duracion_aturdido = 0.4
		cambiar(Estado.ATURDIDO)
	if estado == Estado.ATURDIDO:
		t = 0.0
	vel = rayo_rival.direccion * (4.0 if bloquea else 9.0)
	if vida <= 0.0:
		_caer_ko(rayo_rival.direccion)
	return bloquea


func _recibir_dano(cantidad: float, atacante: Luchador) -> void:
	vida = maxf(vida - cantidad, 0.0)
	if combate != null:
		combate.al_recibir_dano(self, atacante, cantidad)


func _contraataque(atacante: Luchador) -> void:
	ki -= COSTE_ESQUIVA
	var desde := global_position
	var detras := atacante.global_position - atacante.adelante() * 1.8 + Vector3.UP * 0.3
	global_position = detras
	vel = Vector3.ZERO
	cambiar(Estado.RECUPERACION)
	invulnerable = 0.3
	atacante.duracion_aturdido = 0.55
	atacante.cambiar(Estado.ATURDIDO)
	atacante.vel = Vector3.ZERO
	if combate != null:
		combate.al_esquivar(self, desde, detras)


func _lanzar(v: Vector3) -> void:
	cambiar(Estado.LANZADO)
	vel = v
	giro_lanzado = 0.0


func lanzar(v: Vector3) -> void:
	_lanzar(v)


func _caer_ko(dir: Vector3) -> void:
	_cortar_rayo()
	cambiar(Estado.KO)
	vel = dir * 12.0 + Vector3.UP * 5.0
	invulnerable = 0.0
	if combate != null:
		combate.al_ko(self)


func _cortar_rayo() -> void:
	if rayo != null and is_instance_valid(rayo) and not rayo.terminado:
		rayo.terminar()
	rayo = null


func _conectar(info: Dictionary) -> String:
	if rival == null or rival.estado == Estado.KO or distancia() > ALCANCE:
		ultimo_resultado = "fallo"
		return ultimo_resultado
	var frente := -global_transform.basis.z
	if frente.dot(hacia_rival()) < 0.2:
		ultimo_resultado = "fallo"
		return ultimo_resultado
	ultimo_resultado = rival.recibir_golpe(self, info)
	if ultimo_resultado == "golpeado":
		golpes_conectados += 1
		ki = minf(ki + 10.0, KI_MAX)
	elif ultimo_resultado == "bloqueado" or ultimo_resultado == "guardia_rota":
		ki = minf(ki + 4.0, KI_MAX)
	if combate != null and ultimo_resultado in ["golpeado", "bloqueado", "guardia_rota"]:
		combate.al_impactar(self, rival, info, ultimo_resultado)
	return ultimo_resultado


# --- movimiento -----------------------------------------------------------------------------

func _suelo() -> float:
	var base := 0.0
	if combate != null and combate.arena != null:
		base = combate.arena.altura_suelo(global_position)
	return base + ALTURA_PIES


func _mover(dt: float) -> void:
	var pos := global_position + vel * dt
	var suelo := _suelo()
	if pos.y < suelo:
		if estado == Estado.LANZADO and vel.y < -7.0:
			if combate != null:
				combate.impacto_suelo(self, Vector3(pos.x, suelo - ALTURA_PIES, pos.z), -vel.y)
			vel.y = -vel.y * 0.35
			vel.x *= 0.6
			vel.z *= 0.6
		elif vel.y < 0.0:
			vel.y = 0.0
		pos.y = suelo
	pos.y = minf(pos.y, 90.0)
	if combate != null and combate.arena != null:
		pos = combate.arena.limitar(pos)
		var roca: Variant = combate.arena.roca_que_choca(pos, RADIO)
		if roca != null:
			if estado == Estado.LANZADO and vel.length() > 10.0:
				combate.impacto_roca(self, roca, pos)
				vel *= 0.35
			else:
				pos = combate.arena.empujar_fuera(roca, pos, RADIO)
	global_position = pos
	if rival != null and estado != Estado.KO and rival.estado != Estado.KO:
		var dif := global_position - rival.global_position
		var dist := dif.length()
		var minimo := RADIO * 2.0
		if dist < minimo and dist > 0.0001:
			var empuje := dif / dist * (minimo - dist) * 0.5
			global_position += empuje
			rival.global_position -= empuje


func _orientar(dt: float) -> void:
	if rival == null or estado == Estado.LANZADO or estado == Estado.KO:
		return
	var f := adelante()
	var objetivo := atan2(-f.x, -f.z)
	rotation.y = lerp_angle(rotation.y, objetivo, 1.0 - exp(-14.0 * dt))


func mirar_al_rival() -> void:
	var f := adelante()
	rotation.y = atan2(-f.x, -f.z)
