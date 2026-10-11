class_name Rayo
extends Node3D

## Súper ataque: un rayo que sale de las manos y avanza hacia el rival.
## Si se encuentra con el rayo del rival, Combate empieza el choque de rayos.

const ENERGIA := preload("res://shaders/energia.gdshader")
const VELOCIDAD := 75.0
const DURACION_MAX := 2.6
const TIEMPO_IMPACTO := 0.9

var dueno: Luchador
var objetivo: Luchador
var combate: Combate
var origen := Vector3.ZERO
var cabeza := Vector3.ZERO
var direccion := Vector3.FORWARD
var vida := 0.0
var terminado := false
var en_choque := false
var impactando := -1.0  # >= 0 mientras está golpeando al objetivo
var dano_total := 760.0
var multiplicador := 1.0
var color := Color.WHITE

var _exterior: MeshInstance3D
var _nucleo: MeshInstance3D
var _punta: MeshInstance3D
var _mat_exterior: ShaderMaterial
var _luz: OmniLight3D
var _desvanecer := 0.0


func preparar(el_dueno: Luchador, el_combate: Combate) -> void:
	dueno = el_dueno
	objetivo = el_dueno.rival
	combate = el_combate
	var tecnica: Dictionary = dueno.def.get("super", {})
	dano_total = float(tecnica.get("dano", 760.0)) * float(dueno.def.get("fuerza", 1.0))
	origen = dueno.posicion_disparo()
	cabeza = origen
	var hacia := objetivo.global_position - origen
	direccion = hacia.normalized() if hacia.length_squared() > 0.0001 else dueno.adelante()
	var colores: Dictionary = dueno.def["colores"]
	color = colores["ki"]
	_crear_visual(colores)


func paso(dt: float) -> void:
	if terminado:
		_apagarse(dt)
		return
	vida += dt
	origen = dueno.posicion_disparo()
	if en_choque:
		_actualizar_visual()
		return
	if impactando >= 0.0:
		impactando += dt
		objetivo.recibir_rayo(self, dano_total * multiplicador * dt / TIEMPO_IMPACTO)
		cabeza = objetivo.global_position
		if impactando >= TIEMPO_IMPACTO or objetivo.estado == Luchador.Estado.KO:
			if objetivo.estado != Luchador.Estado.KO:
				objetivo.lanzar(direccion * 30.0 + Vector3.UP * 5.0)
			combate.explosion(cabeza, color, 1.6)
			terminar()
		_actualizar_visual()
		return
	var hacia := objetivo.global_position - cabeza
	if hacia.length() > 0.5:
		direccion = direccion.slerp(hacia.normalized(), 1.0 - exp(-2.2 * dt)).normalized()
	cabeza += direccion * VELOCIDAD * dt
	if cabeza.distance_to(objetivo.global_position) < 1.3 and objetivo.estado != Luchador.Estado.KO:
		if objetivo.invulnerable <= 0.0:
			impactando = 0.0
			combate.al_alcanzar_rayo(self)
	elif cabeza.y < combate.arena.altura_suelo(cabeza) + 0.2:
		combate.explosion(cabeza, color, 1.4)
		terminar()
	else:
		var roca: Variant = combate.arena.roca_en(cabeza, 0.6)
		if roca != null:
			combate.arena.romper(roca)
			combate.explosion(cabeza, color, 1.8)
			terminar()
		elif vida >= DURACION_MAX:
			terminar()
	_actualizar_visual()


func terminar() -> void:
	if terminado:
		return
	terminado = true
	en_choque = false
	impactando = -1.0
	_desvanecer = 0.0


func esta_activo() -> bool:
	return not terminado


func _crear_visual(colores: Dictionary) -> void:
	_mat_exterior = ShaderMaterial.new()
	_mat_exterior.shader = ENERGIA
	_mat_exterior.set_shader_parameter("color", colores["ki"])
	_mat_exterior.set_shader_parameter("color_nucleo", colores["ki_nucleo"])
	_mat_exterior.set_shader_parameter("intensidad", 1.5)
	_mat_exterior.set_shader_parameter("velocidad", -9.0)
	_exterior = _malla(_cilindro(0.55), _mat_exterior)

	var mat_nucleo := StandardMaterial3D.new()
	mat_nucleo.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat_nucleo.albedo_color = (colores["ki_nucleo"] as Color) * 1.3
	_nucleo = _malla(_cilindro(0.2), mat_nucleo)

	var mat_punta := ShaderMaterial.new()
	mat_punta.shader = ENERGIA
	mat_punta.set_shader_parameter("color", colores["ki"])
	mat_punta.set_shader_parameter("color_nucleo", colores["ki_nucleo"])
	mat_punta.set_shader_parameter("intensidad", 1.8)
	mat_punta.set_shader_parameter("centro", 0.2)
	var esfera := SphereMesh.new()
	esfera.radius = 1.0
	esfera.height = 2.0
	_punta = _malla(esfera, mat_punta)

	_luz = OmniLight3D.new()
	_luz.light_color = colores["ki"]
	_luz.light_energy = 2.0
	_luz.omni_range = 14.0
	add_child(_luz)
	_actualizar_visual()


func _actualizar_visual() -> void:
	var tramo := cabeza - origen
	var largo := tramo.length()
	if largo < 0.05:
		tramo = direccion * 0.05
		largo = 0.05
	var dir := tramo / largo
	var giro := Basis(Quaternion(Vector3.UP, dir)) if absf(dir.dot(Vector3.UP)) < 0.999 else Basis.IDENTITY
	var centro := origen + tramo * 0.5
	var pulso := 1.0 + sin(vida * 40.0) * 0.06
	_exterior.global_transform = Transform3D(giro * Basis.from_scale(Vector3(pulso, largo, pulso)), centro)
	_nucleo.global_transform = Transform3D(giro * Basis.from_scale(Vector3(1.0, largo, 1.0)), centro)
	_mat_exterior.set_shader_parameter("bandas", maxf(largo / 2.0, 1.0))
	var tam := (1.25 if en_choque else 0.95) * pulso
	_punta.global_transform = Transform3D(Basis.from_scale(Vector3.ONE * tam), cabeza)
	_luz.global_position = cabeza


func _apagarse(dt: float) -> void:
	_desvanecer += dt
	var k := clampf(1.0 - _desvanecer / 0.25, 0.0, 1.0)
	if k <= 0.0:
		visible = false
		return
	origen = dueno.posicion_disparo() if is_instance_valid(dueno) else origen
	_mat_exterior.set_shader_parameter("opacidad", k)
	_exterior.scale = Vector3(k, _exterior.scale.y, k)
	_nucleo.visible = false
	_punta.scale = Vector3.ONE * k
	_luz.light_energy = 2.0 * k


func _malla(malla: Mesh, mat: Material) -> MeshInstance3D:
	var m := MeshInstance3D.new()
	m.mesh = malla
	m.material_override = mat
	m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(m)
	return m


static func _cilindro(radio: float) -> CylinderMesh:
	var m := CylinderMesh.new()
	m.top_radius = radio
	m.bottom_radius = radio
	m.height = 1.0
	m.radial_segments = 16
	m.rings = 1
	return m
