class_name CamaraCombate
extends Camera3D

## Cámara fija en el rival: detrás del jugador, algo ladeada, mirando hacia el combate.
## Hace un plano corto del que lanza un súper y tiembla con los golpes fuertes.

var objetivo: Luchador
var rival: Luchador
var distancia := 5.6
var altura := 1.5
var lateral := 1.1
var temblores := true

var _temblor := 0.0
var _foco: Luchador = null
var _foco_t := 0.0


func preparar(a: Luchador, b: Luchador) -> void:
	objetivo = a
	rival = b
	fov = 62.0
	near = 0.1
	far = 1500.0
	_colocar(1.0)


func temblar(fuerza: float) -> void:
	if temblores:
		_temblor = maxf(_temblor, fuerza)


func enfocar(l: Luchador, duracion: float) -> void:
	_foco = l
	_foco_t = duracion


func paso(dt: float) -> void:
	if objetivo == null or rival == null:
		return
	if _foco_t > 0.0 and _foco != null:
		_foco_t -= dt
		var f := _foco.adelante()
		var lado := f.cross(Vector3.UP)
		var deseada := _foco.global_position + f * 3.4 + lado * 1.7 + Vector3.UP * 0.5
		global_position = global_position.lerp(deseada, 1.0 - exp(-10.0 * dt))
		_mirar(_foco.global_position + Vector3.UP * 0.35)
	else:
		_colocar(1.0 - exp(-7.0 * dt))
	if _temblor > 0.0:
		h_offset = randf_range(-1.0, 1.0) * _temblor * 0.22
		v_offset = randf_range(-1.0, 1.0) * _temblor * 0.22
		_temblor = maxf(_temblor - dt * 2.5, 0.0)
	else:
		h_offset = 0.0
		v_offset = 0.0


func _colocar(suavizado: float) -> void:
	var a := objetivo.global_position
	var b := rival.global_position
	var plano := b - a
	plano.y = 0.0
	if plano.length() < 0.1:
		plano = -objetivo.global_transform.basis.z
		plano.y = 0.0
	var f := plano.normalized()
	var r := f.cross(Vector3.UP)
	var lejos := clampf(a.distance_to(b) / 40.0, 0.0, 1.0)
	var deseada := a - f * (distancia + lejos * 2.0) + Vector3.UP * (altura + lejos * 0.8) + r * lateral
	deseada.y += clampf((a.y - b.y) * 0.15, -2.0, 2.0)
	global_position = global_position.lerp(deseada, suavizado)
	global_position.y = maxf(global_position.y, 0.5)
	_mirar(a.lerp(b, 0.6) + Vector3.UP * 0.5)


func _mirar(punto: Vector3) -> void:
	var dif := punto - global_position
	if dif.length() < 0.01 or absf(dif.normalized().dot(Vector3.UP)) > 0.98:
		return
	look_at(punto, Vector3.UP)
