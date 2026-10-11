class_name RafagaKi
extends Node3D

## Bola de ki que persigue un poco al rival.

const ENERGIA := preload("res://shaders/energia.gdshader")

var dueno: Luchador
var objetivo: Luchador
var direccion := Vector3.FORWARD
var velocidad := 38.0
var vida := 2.2
var dano := 32.0
var terminado := false
var _malla: MeshInstance3D


func preparar(el_dueno: Luchador, desde: Vector3) -> void:
	dueno = el_dueno
	objetivo = el_dueno.rival
	dano = 32.0 * float(dueno.def.get("fuerza", 1.0))
	global_position = desde
	var hacia := objetivo.global_position - desde
	direccion = hacia.normalized() if hacia.length_squared() > 0.0001 else dueno.adelante()
	var colores: Dictionary = dueno.def["colores"]
	var mat := ShaderMaterial.new()
	mat.shader = ENERGIA
	mat.set_shader_parameter("color", colores["ki"])
	mat.set_shader_parameter("color_nucleo", colores["ki_nucleo"])
	mat.set_shader_parameter("intensidad", 1.7)
	mat.set_shader_parameter("velocidad", 6.0)
	_malla = MeshInstance3D.new()
	var esfera := SphereMesh.new()
	esfera.radius = 0.3
	esfera.height = 0.6
	esfera.radial_segments = 16
	esfera.rings = 8
	_malla.mesh = esfera
	_malla.material_override = mat
	_malla.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_malla.scale = Vector3(1.0, 1.0, 1.7)
	add_child(_malla)
	_orientar()


func paso(dt: float) -> void:
	if terminado:
		return
	vida -= dt
	var hacia := objetivo.global_position - global_position
	if hacia.length() > 3.0:
		direccion = direccion.slerp(hacia.normalized(), 1.0 - exp(-1.8 * dt)).normalized()
	global_position += direccion * velocidad * dt
	_orientar()
	if vida <= 0.0:
		terminar()


func terminar() -> void:
	terminado = true
	visible = false


func _orientar() -> void:
	if absf(direccion.dot(Vector3.UP)) < 0.99:
		_malla.basis = Basis.looking_at(direccion, Vector3.UP).scaled_local(Vector3(1.0, 1.0, 1.7))
