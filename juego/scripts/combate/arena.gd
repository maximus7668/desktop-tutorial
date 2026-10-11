class_name Arena
extends Node3D

## Escenario: llanura con mesetas de roca que se rompen, montañas al fondo, nubes y cielo.

signal roca_rota(roca: Dictionary)

const TOON := preload("res://shaders/toon.gdshader")
const SUELO := preload("res://shaders/suelo.gdshader")
const CONTORNO := preload("res://shaders/contorno.gdshader")
const RADIO := 150.0
const ESTRECHAMIENTO := 0.9  # las mesetas son algo más estrechas arriba

var rocas: Array[Dictionary] = []
var entorno: WorldEnvironment
var sol: DirectionalLight3D
var _mat_roca: ShaderMaterial
var _mat_cima: ShaderMaterial
var _mat_escombro: ShaderMaterial


func construir(semilla := 7, sombras := true) -> void:
	_cielo(sombras)
	_materiales()
	_suelo()
	_rocas(semilla)
	_montanas(semilla)
	_nubes(semilla)


# --- consultas para el combate ---------------------------------------------------------------

func altura_suelo(_pos: Vector3) -> float:
	return 0.0


func limitar(pos: Vector3) -> Vector3:
	var plano := Vector2(pos.x, pos.z)
	if plano.length() > RADIO:
		plano = plano.normalized() * RADIO
		pos.x = plano.x
		pos.z = plano.y
	return pos


func roca_que_choca(pos: Vector3, radio: float) -> Variant:
	return roca_en(pos, radio)


func roca_en(pos: Vector3, radio: float) -> Variant:
	for roca: Dictionary in rocas:
		if not roca["viva"]:
			continue
		if pos.y - radio > roca["altura"]:
			continue
		var base: Vector3 = roca["pos"]
		var d := Vector2(pos.x - base.x, pos.z - base.z).length()
		if d < float(roca["radio"]) * ESTRECHAMIENTO + radio:
			return roca
	return null


func empujar_fuera(roca: Dictionary, pos: Vector3, radio: float) -> Vector3:
	var base: Vector3 = roca["pos"]
	var plano := Vector2(pos.x - base.x, pos.z - base.z)
	if plano.length_squared() < 0.0001:
		plano = Vector2(1, 0)
	plano = plano.normalized() * (float(roca["radio"]) * ESTRECHAMIENTO + radio + 0.01)
	return Vector3(base.x + plano.x, pos.y, base.z + plano.y)


## Resta vida a la roca. Devuelve true si se ha roto.
func danar(roca: Dictionary, cantidad: float) -> bool:
	if not roca["viva"]:
		return false
	roca["vida"] = float(roca["vida"]) - cantidad
	if float(roca["vida"]) <= 0.0:
		romper(roca)
		return true
	return false


func romper(roca: Dictionary) -> void:
	if not roca["viva"]:
		return
	roca["viva"] = false
	(roca["nodo"] as Node3D).visible = false
	_escombros(roca)
	roca_rota.emit(roca)


func rocas_vivas() -> int:
	var n := 0
	for roca: Dictionary in rocas:
		if roca["viva"]:
			n += 1
	return n


# --- construcción -------------------------------------------------------------------------------

func _cielo(sombras: bool) -> void:
	var cielo := ProceduralSkyMaterial.new()
	cielo.sky_top_color = Color(0.13, 0.33, 0.85)
	cielo.sky_horizon_color = Color(0.68, 0.83, 1.0)
	cielo.ground_horizon_color = Color(0.68, 0.83, 1.0)
	cielo.ground_bottom_color = Color(0.32, 0.42, 0.55)
	cielo.sun_angle_max = 25.0
	var sky := Sky.new()
	sky.sky_material = cielo
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.78, 0.8, 0.98)
	env.ambient_light_energy = 0.32
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	env.glow_enabled = true
	env.glow_intensity = 0.55
	env.glow_bloom = 0.0
	env.glow_hdr_threshold = 1.15
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_ADDITIVE
	env.fog_enabled = true
	env.fog_light_color = Color(0.7, 0.82, 0.98)
	env.fog_density = 0.0016
	env.fog_sky_affect = 0.0
	entorno = WorldEnvironment.new()
	entorno.environment = env
	add_child(entorno)
	sol = DirectionalLight3D.new()
	sol.rotation_degrees = Vector3(-50, -35, 0)
	sol.light_energy = 1.2
	sol.light_color = Color(1.0, 0.97, 0.9)
	sol.shadow_enabled = sombras
	sol.directional_shadow_max_distance = 140.0
	add_child(sol)


func _materiales() -> void:
	var contorno := ShaderMaterial.new()
	contorno.shader = CONTORNO
	contorno.set_shader_parameter("grosor", 0.12)
	_mat_roca = _toon(Color(0.78, 0.6, 0.45), Color(0.6, 0.5, 0.78), contorno)
	_mat_cima = _toon(Color(0.42, 0.66, 0.32), Color(0.55, 0.55, 0.8), contorno)
	_mat_escombro = _toon(Color(0.7, 0.55, 0.42), Color(0.6, 0.5, 0.78), null)


func _toon(color: Color, sombra: Color, contorno: Material) -> ShaderMaterial:
	var mat := ShaderMaterial.new()
	mat.shader = TOON
	mat.set_shader_parameter("color_base", color)
	mat.set_shader_parameter("color_sombra", sombra)
	mat.set_shader_parameter("brillo_borde", 0.2)
	if contorno != null:
		mat.next_pass = contorno
	return mat


func _suelo() -> void:
	var plano := PlaneMesh.new()
	plano.size = Vector2(RADIO * 5.0, RADIO * 5.0)
	var mat := ShaderMaterial.new()
	mat.shader = SUELO
	var suelo := MeshInstance3D.new()
	suelo.name = "Suelo"
	suelo.mesh = plano
	suelo.material_override = mat
	add_child(suelo)


func _rocas(semilla: int) -> void:
	var azar := RandomNumberGenerator.new()
	azar.seed = semilla
	var intentos := 0
	while rocas.size() < 26 and intentos < 400:
		intentos += 1
		var angulo := azar.randf() * TAU
		var distancia := azar.randf_range(24.0, RADIO - 12.0)
		var pos := Vector3(cos(angulo) * distancia, 0.0, sin(angulo) * distancia)
		var radio := azar.randf_range(3.0, 8.0)
		var libre := true
		for otra: Dictionary in rocas:
			if (otra["pos"] as Vector3).distance_to(pos) < float(otra["radio"]) + radio + 7.0:
				libre = false
				break
		if not libre:
			continue
		var altura := azar.randf_range(8.0, 28.0)
		var nodo := _meseta(pos, radio, altura, azar.randf() * TAU)
		rocas.append({"pos": pos, "radio": radio, "altura": altura, "nodo": nodo, "vida": 300.0, "viva": true})


func _meseta(pos: Vector3, radio: float, altura: float, giro: float) -> Node3D:
	var nodo := Node3D.new()
	nodo.position = pos
	nodo.rotation.y = giro
	add_child(nodo)
	var cuerpo := CylinderMesh.new()
	cuerpo.top_radius = radio * 0.82
	cuerpo.bottom_radius = radio
	cuerpo.height = altura
	cuerpo.radial_segments = 7
	cuerpo.rings = 2
	var m := MeshInstance3D.new()
	m.mesh = cuerpo
	m.position.y = altura * 0.5
	m.material_override = _mat_roca
	nodo.add_child(m)
	var cima := CylinderMesh.new()
	cima.top_radius = radio * 0.8
	cima.bottom_radius = radio * 0.86
	cima.height = 0.9
	cima.radial_segments = 7
	cima.rings = 1
	var c := MeshInstance3D.new()
	c.mesh = cima
	c.position.y = altura + 0.3
	c.material_override = _mat_cima
	nodo.add_child(c)
	return nodo


func _escombros(roca: Dictionary) -> void:
	var azar := RandomNumberGenerator.new()
	azar.seed = int((roca["pos"] as Vector3).x * 1000.0)
	var base: Vector3 = roca["pos"]
	for i in 6:
		var caja := BoxMesh.new()
		var tam := azar.randf_range(1.0, 2.6)
		caja.size = Vector3(tam, tam * 0.7, tam)
		var m := MeshInstance3D.new()
		m.mesh = caja
		m.material_override = _mat_escombro
		var angulo := azar.randf() * TAU
		var d := azar.randf_range(0.0, float(roca["radio"]))
		m.position = base + Vector3(cos(angulo) * d, tam * 0.3, sin(angulo) * d)
		m.rotation = Vector3(azar.randf_range(-0.4, 0.4), azar.randf() * TAU, azar.randf_range(-0.4, 0.4))
		add_child(m)


func _montanas(semilla: int) -> void:
	var azar := RandomNumberGenerator.new()
	azar.seed = semilla + 101
	var mat := _toon(Color(0.42, 0.5, 0.78), Color(0.55, 0.6, 0.9), null)
	var nieve := _toon(Color(0.95, 0.97, 1.0), Color(0.7, 0.75, 0.95), null)
	for i in 22:
		var angulo := TAU * i / 22.0 + azar.randf_range(-0.1, 0.1)
		var distancia := azar.randf_range(330.0, 430.0)
		var alto := azar.randf_range(70.0, 160.0)
		var ancho := alto * azar.randf_range(0.8, 1.3)
		var cono := CylinderMesh.new()
		cono.top_radius = 0.0
		cono.bottom_radius = ancho
		cono.height = alto
		cono.radial_segments = 6
		cono.rings = 1
		var m := MeshInstance3D.new()
		m.mesh = cono
		m.material_override = mat
		m.position = Vector3(cos(angulo) * distancia, alto * 0.5 - 2.0, sin(angulo) * distancia)
		m.rotation.y = azar.randf() * TAU
		m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(m)
		var cima := CylinderMesh.new()
		cima.top_radius = 0.0
		cima.bottom_radius = ancho * 0.22
		cima.height = alto * 0.22
		cima.radial_segments = 6
		cima.rings = 1
		var n := MeshInstance3D.new()
		n.mesh = cima
		n.material_override = nieve
		n.position = m.position + Vector3.UP * (alto * 0.5 - alto * 0.11 + 0.5)
		n.rotation.y = m.rotation.y
		n.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(n)


func _nubes(semilla: int) -> void:
	var azar := RandomNumberGenerator.new()
	azar.seed = semilla + 202
	var mat := _toon(Color(1.0, 1.0, 1.0), Color(0.75, 0.8, 0.98), null)
	mat.set_shader_parameter("brillo_borde", 0.0)
	for i in 14:
		var centro := Vector3(azar.randf_range(-280.0, 280.0), azar.randf_range(70.0, 110.0), azar.randf_range(-280.0, 280.0))
		for j in 4:
			var esfera := SphereMesh.new()
			var r := azar.randf_range(8.0, 16.0)
			esfera.radius = r
			esfera.height = r * 2.0
			esfera.radial_segments = 12
			esfera.rings = 6
			var m := MeshInstance3D.new()
			m.mesh = esfera
			m.material_override = mat
			m.position = centro + Vector3(azar.randf_range(-16.0, 16.0), azar.randf_range(-2.0, 4.0), azar.randf_range(-10.0, 10.0))
			m.scale = Vector3(1.6, 0.6, 1.0)
			m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(m)
