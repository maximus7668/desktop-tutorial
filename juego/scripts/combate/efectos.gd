class_name Efectos
extends Node3D

## Destellos, ondas de choque, chispas, escombros y estelas. Cada efecto se borra solo.

signal temblor(fuerza: float)

var _vivos: Array[Dictionary] = []


func destello(pos: Vector3, color: Color, tam := 1.0, duracion := 0.18) -> void:
	var esfera := SphereMesh.new()
	esfera.radius = 0.5
	esfera.height = 1.0
	esfera.radial_segments = 16
	esfera.rings = 8
	var m := _malla(esfera, color, pos)
	_vivos.append({"nodo": m, "t": 0.0, "dur": duracion, "tipo": "destello", "tam": tam, "color": color})


func onda(pos: Vector3, color: Color, tam := 3.0, duracion := 0.35, normal := Vector3.UP) -> void:
	var aro := TorusMesh.new()
	aro.inner_radius = 0.42
	aro.outer_radius = 0.5
	aro.rings = 32
	aro.ring_segments = 6
	var m := _malla(aro, color, pos)
	if absf(normal.normalized().dot(Vector3.UP)) < 0.999:
		m.basis = Basis(Quaternion(Vector3.UP, normal.normalized()))
	_vivos.append({"nodo": m, "t": 0.0, "dur": duracion, "tipo": "onda", "tam": tam, "color": color})


func estela(pos: Vector3, color: Color) -> void:
	var capsula := CapsuleMesh.new()
	capsula.radius = 0.45
	capsula.height = 2.0
	var m := _malla(capsula, color, pos)
	_vivos.append({"nodo": m, "t": 0.0, "dur": 0.35, "tipo": "estela", "tam": 1.0, "color": color})


func chispas(pos: Vector3, color: Color, cantidad := 14, velocidad := 9.0) -> void:
	var p := CPUParticles3D.new()
	p.position = pos
	p.amount = cantidad
	p.lifetime = 0.35
	p.one_shot = true
	p.explosiveness = 1.0
	p.direction = Vector3.UP
	p.spread = 180.0
	p.gravity = Vector3.ZERO
	p.initial_velocity_min = velocidad * 0.5
	p.initial_velocity_max = velocidad
	p.scale_amount_min = 0.6
	p.scale_amount_max = 1.2
	var malla := BoxMesh.new()
	malla.size = Vector3(0.05, 0.05, 0.35)
	p.mesh = malla
	p.particle_flag_align_y = true
	var mat := _material(color * 1.4)
	p.material_override = mat
	add_child(p)
	p.emitting = true
	_vivos.append({"nodo": p, "t": 0.0, "dur": 0.45, "tipo": "particulas", "tam": 1.0, "color": color})


func escombros(pos: Vector3, color: Color, cantidad := 12) -> void:
	var p := CPUParticles3D.new()
	p.position = pos
	p.amount = cantidad
	p.lifetime = 1.3
	p.one_shot = true
	p.explosiveness = 1.0
	p.direction = Vector3.UP
	p.spread = 70.0
	p.gravity = Vector3(0, -24, 0)
	p.initial_velocity_min = 7.0
	p.initial_velocity_max = 15.0
	p.angular_velocity_min = -360.0
	p.angular_velocity_max = 360.0
	p.scale_amount_min = 0.4
	p.scale_amount_max = 1.1
	var malla := BoxMesh.new()
	malla.size = Vector3(0.5, 0.4, 0.5)
	p.mesh = malla
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	p.material_override = mat
	add_child(p)
	p.emitting = true
	_vivos.append({"nodo": p, "t": 0.0, "dur": 1.4, "tipo": "particulas", "tam": 1.0, "color": color})


func paso(dt: float) -> void:
	var quedan: Array[Dictionary] = []
	for e: Dictionary in _vivos:
		var nodo: Node3D = e["nodo"]
		if not is_instance_valid(nodo):
			continue
		e["t"] = float(e["t"]) + dt
		var k := clampf(float(e["t"]) / float(e["dur"]), 0.0, 1.0)
		var tam: float = e["tam"]
		match e["tipo"]:
			"destello":
				nodo.scale = Vector3.ONE * tam * (0.4 + 1.3 * k)
				_alfa(nodo, 1.0 - k)
			"onda":
				var escala := tam * (0.3 + 2.2 * k)
				nodo.scale = Vector3(escala, escala * 0.6, escala)
				_alfa(nodo, 1.0 - k)
			"estela":
				nodo.scale = Vector3(1.0 + k * 0.4, 1.0, 1.0 + k * 0.4)
				_alfa(nodo, 0.8 * (1.0 - k))
		if k >= 1.0:
			nodo.queue_free()
		else:
			quedan.append(e)
	_vivos = quedan


func cantidad_vivos() -> int:
	return _vivos.size()


func _malla(malla: Mesh, color: Color, pos: Vector3) -> MeshInstance3D:
	var m := MeshInstance3D.new()
	m.mesh = malla
	m.material_override = _material(color)
	m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	m.position = pos
	add_child(m)
	return m


func _material(color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.albedo_color = color
	return mat


func _alfa(nodo: Node3D, a: float) -> void:
	if nodo is MeshInstance3D:
		var mat := (nodo as MeshInstance3D).material_override as StandardMaterial3D
		if mat != null:
			var c := mat.albedo_color
			c.a = clampf(a, 0.0, 1.0)
			mat.albedo_color = c
