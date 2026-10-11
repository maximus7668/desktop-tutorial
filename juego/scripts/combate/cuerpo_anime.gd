class_name CuerpoAnime
extends Node3D

## Cuerpo provisional hecho con primitivas, con sombreado anime y contorno.
## Cuando la fábrica entrega el modelo de verdad, usar_modelo() lo pone en su lugar.

const TOON := preload("res://shaders/toon.gdshader")
const CONTORNO := preload("res://shaders/contorno.gdshader")
const ENERGIA := preload("res://shaders/energia.gdshader")

# Mechones del pelo en punta: [dirección, largo, radio, base (opcional, si no sale del centro)].
const MECHONES_PUNTAS := [
	[Vector3(0, 1, 0.25), 0.3, 0.075],
	[Vector3(0.35, 0.9, 0.35), 0.28, 0.07],
	[Vector3(-0.35, 0.9, 0.35), 0.28, 0.07],
	[Vector3(0.15, 0.7, 0.8), 0.32, 0.075],
	[Vector3(-0.15, 0.7, 0.8), 0.32, 0.075],
	[Vector3(0.62, 0.55, 0.55), 0.24, 0.065],
	[Vector3(-0.62, 0.55, 0.55), 0.24, 0.065],
	[Vector3(0.0, 0.4, 1.0), 0.3, 0.07],
	[Vector3(0.42, 0.25, 0.9), 0.24, 0.06],
	[Vector3(-0.42, 0.25, 0.9), 0.24, 0.06],
	[Vector3(0.8, 0.25, 0.3), 0.18, 0.055],
	[Vector3(-0.8, 0.25, 0.3), 0.18, 0.055],
	[Vector3(0.12, 0.85, -0.55), 0.22, 0.065],
	[Vector3(-0.22, 0.8, -0.5), 0.2, 0.06],
	[Vector3(0.25, -0.55, -0.8), 0.14, 0.045, Vector3(0.04, 0.29, -0.1)],
	[Vector3(-0.1, -0.6, -0.8), 0.12, 0.04, Vector3(-0.05, 0.29, -0.11)],
]

const MECHONES_COLETA := [
	[Vector3(0.1, -0.55, -0.83), 0.15, 0.05, Vector3(0.06, 0.28, -0.1)],
	[Vector3(-0.12, -0.55, -0.83), 0.15, 0.05, Vector3(-0.06, 0.28, -0.1)],
	[Vector3(0.0, -0.6, -0.8), 0.13, 0.045, Vector3(0.0, 0.29, -0.11)],
	[Vector3(0.12, -1.0, -0.1), 0.28, 0.045, Vector3(0.13, 0.21, -0.05)],
	[Vector3(-0.12, -1.0, -0.1), 0.28, 0.045, Vector3(-0.13, 0.21, -0.05)],
]

var def: Dictionary = {}
var partes: Node3D
var articulaciones: Dictionary = {}
var actual: Dictionary = {}
var aura: MeshInstance3D
var bola: MeshInstance3D
var mano_d: Node3D
var mano_i: Node3D
var coleta: Node3D
var cintas: Array[Node3D] = []
var modelo: Node3D = null
var animaciones: AnimationPlayer = null

var _materiales: Dictionary = {}
var _contorno: ShaderMaterial
var _aura_mat: ShaderMaterial
var _aura_fuerza := 0.0
var _tiempo := 0.0
var _anim_actual := ""


func construir(datos: Dictionary) -> void:
	def = datos
	var c: Dictionary = datos["colores"]
	_contorno = ShaderMaterial.new()
	_contorno.shader = CONTORNO
	partes = Node3D.new()
	partes.name = "Partes"
	add_child(partes)

	var pelvis := _articulacion("pelvis", partes, Vector3.ZERO)
	_pieza(pelvis, _capsula(0.16, 0.44), Vector3(0, -0.02, 0), c["abajo"], Vector3(0, 0, 90))
	var torso := _articulacion("torso", pelvis, Vector3(0, 0.06, 0))
	_pieza(torso, _capsula(0.2, 0.62), Vector3(0, 0.3, 0), c["arriba"], Vector3.ZERO, Vector3(1.12, 1.0, 0.78))
	_pieza(torso, _cilindro(0.21, 0.21, 0.07), Vector3(0, 0.05, 0), c["ribete"], Vector3.ZERO, Vector3(1.1, 1.0, 0.85))
	_pieza(torso, _caja(Vector3(0.05, 0.4, 0.02)), Vector3(0.0, 0.36, -0.16), c["ribete"], Vector3(-8, 0, 0), Vector3.ONE, false)

	var cabeza := _articulacion("cabeza", torso, Vector3(0, 0.64, 0))
	_pieza(cabeza, _cilindro(0.06, 0.065, 0.14), Vector3(0, 0.03, 0), c["piel"])
	_pieza(cabeza, _esfera(0.15), Vector3(0, 0.17, 0), c["piel"], Vector3.ZERO, Vector3(0.95, 1.08, 1.0))
	_ojos(cabeza, c)
	_pelo(cabeza, c)

	for lado: int in [1, -1]:
		var sufijo := "_d" if lado == 1 else "_i"
		var hombro := _articulacion("hombro" + sufijo, torso, Vector3(0.28 * lado, 0.5, 0))
		_pieza(hombro, _esfera(0.1), Vector3.ZERO, c["arriba"])
		_pieza(hombro, _capsula(0.07, 0.36), Vector3(0, -0.16, 0), c["arriba"])
		var codo := _articulacion("codo" + sufijo, hombro, Vector3(0, -0.32, 0))
		var color_antebrazo: Color = c["arriba"] if datos.get("mangas", "") == "largas" else c["manos"]
		_pieza(codo, _capsula(0.062, 0.32), Vector3(0, -0.15, 0), color_antebrazo)
		var mano := _pieza(codo, _esfera(0.082), Vector3(0, -0.33, 0), c["manos"])
		if lado == 1:
			mano_d = mano
		else:
			mano_i = mano

		var cadera := _articulacion("cadera" + sufijo, pelvis, Vector3(0.13 * lado, -0.06, 0))
		_pieza(cadera, _capsula(0.092, 0.5), Vector3(0, -0.23, 0), c["abajo"])
		var rodilla := _articulacion("rodilla" + sufijo, cadera, Vector3(0, -0.46, 0))
		_pieza(rodilla, _capsula(0.076, 0.46), Vector3(0, -0.21, 0), c["abajo"])
		_pieza(rodilla, _cilindro(0.088, 0.092, 0.2), Vector3(0, -0.34, 0), c["botas"])
		_pieza(rodilla, _caja(Vector3(0.13, 0.09, 0.27)), Vector3(0, -0.46, -0.05), c["botas"])

	_crear_aura(c)
	for nombre: String in Poses.ARTICULACIONES:
		actual[nombre] = Poses.BASE[nombre]
		articulaciones[nombre].rotation_degrees = actual[nombre]


## Sustituye el cuerpo provisional por el modelo que ha hecho la fábrica.
func usar_modelo(escena: PackedScene) -> bool:
	var instancia := escena.instantiate()
	if not instancia is Node3D:
		instancia.free()
		return false
	modelo = instancia
	add_child(modelo)
	# El modelo trae los pies en y = 0 y mira hacia +Z (convención glTF); el luchador tiene
	# el origen en la pelvis y mira hacia -Z.
	modelo.position.y = -Luchador.ALTURA_PIES
	modelo.rotation.y = PI
	partes.visible = false
	animaciones = _buscar_animaciones(modelo)
	return true


func posicion_mano(derecha: bool) -> Vector3:
	return (mano_d if derecha else mano_i).global_position


func posicion_manos() -> Vector3:
	return (mano_d.global_position + mano_i.global_position) * 0.5


func actualizar(dt: float, l: Luchador) -> void:
	_tiempo += dt
	var objetivo := _pose_objetivo(l)
	var rapida := l.estado in [
		Luchador.Estado.GOLPE, Luchador.Estado.GOLPE_FUERTE, Luchador.Estado.RAFAGA,
		Luchador.Estado.PASO, Luchador.Estado.EMBESTIDA,
	]
	var k := 1.0 - exp(-(26.0 if rapida else 11.0) * dt)
	var local := l.global_transform.basis.inverse() * l.vel
	var inclinacion := Vector3(clampf(local.z * 1.4, -32.0, 32.0), 0.0, clampf(-local.x * 1.4, -28.0, 28.0))
	var giro_directo := false
	match l.estado:
		Luchador.Estado.LANZADO:
			inclinacion = Vector3(rad_to_deg(l.giro_lanzado), 0.0, 0.0)
			giro_directo = true
		Luchador.Estado.RECUPERACION:
			inclinacion = Vector3(-360.0 * clampf(l.t / 0.3, 0.0, 1.0), 0.0, 0.0)
			giro_directo = true
		Luchador.Estado.KO:
			inclinacion = Vector3(90.0 if l.en_suelo() else 50.0, 0.0, 0.0)

	for nombre: String in Poses.ARTICULACIONES:
		var meta: Vector3 = objetivo[nombre]
		if nombre == "pelvis":
			meta += inclinacion
			if giro_directo:
				actual[nombre] = meta
				articulaciones[nombre].rotation_degrees = meta
				continue
		actual[nombre] = (actual[nombre] as Vector3).lerp(meta, k)
		articulaciones[nombre].rotation_degrees = actual[nombre]

	var flotando := l.estado in [Luchador.Estado.LIBRE, Luchador.Estado.PRESENTACION, Luchador.Estado.VICTORIA]
	var altura_meta := sin(_tiempo * 2.6) * 0.05 if flotando else 0.0
	if l.estado == Luchador.Estado.KO and l.en_suelo():
		altura_meta = -0.82
	partes.position.y = lerpf(partes.position.y, altura_meta, 1.0 - exp(-8.0 * dt))
	var tiembla := l.estado in [Luchador.Estado.CARGANDO_KI, Luchador.Estado.SUPER_CARGA, Luchador.Estado.CHOQUE]
	partes.position.x = randf_range(-0.012, 0.012) if tiembla else 0.0

	_actualizar_aura(dt, l)
	_actualizar_pelo(local)
	if modelo != null:
		_actualizar_modelo(l)


func _pose_objetivo(l: Luchador) -> Dictionary:
	match l.estado:
		Luchador.Estado.PRESENTACION:
			return Poses.obtener("cargar" if l.t < 1.4 else "presentacion")
		Luchador.Estado.LIBRE:
			return Poses.obtener("correr" if l.corriendo else "base")
		Luchador.Estado.EMBESTIDA:
			return Poses.obtener("embestida")
		Luchador.Estado.PREPARA_GOLPE:
			return Poses.obtener("fuerte_prep" if l.t >= Luchador.TIEMPO_CARGA_GOLPE else "base")
		Luchador.Estado.GOLPE:
			if l.paso_combo >= 5 and l.t < Luchador.TIEMPO_GOLPE_INICIO:
				return Poses.obtener("remate_prep")
			var nombres := ["golpe_d", "golpe_i", "patada_d", "patada_i", "remate"]
			return Poses.obtener(nombres[clampi(l.paso_combo - 1, 0, 4)])
		Luchador.Estado.GOLPE_FUERTE:
			return Poses.obtener("fuerte_prep" if l.t < Luchador.TIEMPO_FUERTE_INICIO else "fuerte")
		Luchador.Estado.RAFAGA:
			return Poses.obtener("rafaga_d" if l.mano_rafaga == 0 else "rafaga_i")
		Luchador.Estado.CARGANDO_KI:
			return Poses.obtener("cargar")
		Luchador.Estado.GUARDIA:
			return Poses.obtener("guardia")
		Luchador.Estado.PASO:
			return Poses.obtener("paso")
		Luchador.Estado.SUPER_CARGA:
			return Poses.obtener("super_carga")
		Luchador.Estado.SUPER_RAYO, Luchador.Estado.CHOQUE:
			return Poses.obtener("super_rayo")
		Luchador.Estado.ATURDIDO:
			return Poses.obtener("aturdido")
		Luchador.Estado.LANZADO:
			return Poses.obtener("lanzado")
		Luchador.Estado.RECUPERACION:
			return Poses.obtener("recuperacion")
		Luchador.Estado.KO:
			return Poses.obtener("ko")
		Luchador.Estado.VICTORIA:
			return Poses.obtener("victoria")
	return Poses.obtener("base")


func _actualizar_aura(dt: float, l: Luchador) -> void:
	var fuerza := 0.0
	match l.estado:
		Luchador.Estado.CARGANDO_KI, Luchador.Estado.SUPER_CARGA, Luchador.Estado.CHOQUE:
			fuerza = 1.0
		Luchador.Estado.PRESENTACION:
			fuerza = 0.8 if l.t < 1.4 else 0.0
		Luchador.Estado.EMBESTIDA:
			fuerza = 0.45
		Luchador.Estado.LIBRE:
			fuerza = 0.35 if l.corriendo else 0.0
	_aura_fuerza = lerpf(_aura_fuerza, fuerza, 1.0 - exp(-10.0 * dt))
	aura.visible = _aura_fuerza > 0.02
	if aura.visible:
		_aura_mat.set_shader_parameter("opacidad", _aura_fuerza)
		var pulso := 1.0 + sin(_tiempo * 18.0) * 0.04
		aura.scale = Vector3(pulso, 1.0 + sin(_tiempo * 13.0) * 0.03, pulso) * (0.85 + 0.25 * _aura_fuerza)
	bola.visible = l.estado == Luchador.Estado.SUPER_CARGA
	if bola.visible:
		bola.global_position = posicion_manos() + Vector3.UP * 0.15
		bola.scale = Vector3.ONE * (0.3 + 1.4 * clampf(l.t / Luchador.TIEMPO_SUPER_CARGA, 0.0, 1.0))


func _actualizar_pelo(local: Vector3) -> void:
	if coleta != null:
		coleta.rotation_degrees = Vector3(
			8.0 + sin(_tiempo * 3.2) * 6.0 + clampf(-local.z * 1.5, -30.0, 30.0),
			sin(_tiempo * 2.1) * 8.0 + clampf(local.x * 1.5, -25.0, 25.0),
			0.0)
	for i in cintas.size():
		var cinta := cintas[i]
		cinta.rotation_degrees = Vector3(
			-10.0 + sin(_tiempo * 9.0 + i) * 10.0 + clampf(-local.z * 1.2, -20.0, 30.0),
			(14.0 if i == 0 else -14.0) + sin(_tiempo * 7.0 + i * 2.0) * 12.0,
			0.0)


func _actualizar_modelo(l: Luchador) -> void:
	if animaciones == null:
		return
	var deseada := _animacion_para(l)
	if deseada.is_empty() or deseada == _anim_actual:
		return
	_anim_actual = deseada
	animaciones.play(deseada, 0.12)


func _animacion_para(l: Luchador) -> String:
	var candidatas: Array = []
	match l.estado:
		Luchador.Estado.LIBRE, Luchador.Estado.PRESENTACION:
			candidatas = ["volar", "correr"] if l.corriendo else ["guardia", "idle"]
		Luchador.Estado.EMBESTIDA:
			candidatas = ["volar", "correr"]
		Luchador.Estado.GOLPE:
			candidatas = ["patada", "golpe_debil"] if l.paso_combo in [3, 4] else (["golpe_fuerte"] if l.paso_combo >= 5 else ["golpe_debil"])
		Luchador.Estado.GOLPE_FUERTE:
			candidatas = ["golpe_fuerte"]
		Luchador.Estado.RAFAGA:
			candidatas = ["rafaga"]
		Luchador.Estado.CARGANDO_KI:
			candidatas = ["cargar_ki"]
		Luchador.Estado.GUARDIA:
			candidatas = ["guardia"]
		Luchador.Estado.PASO:
			candidatas = ["esquivar", "teletransporte"]
		Luchador.Estado.SUPER_CARGA, Luchador.Estado.SUPER_RAYO, Luchador.Estado.CHOQUE:
			candidatas = ["tecnica"]
		Luchador.Estado.ATURDIDO:
			candidatas = ["recibir_golpe"]
		Luchador.Estado.LANZADO, Luchador.Estado.KO:
			candidatas = ["derribado"]
		Luchador.Estado.VICTORIA:
			candidatas = ["victoria", "guardia"]
	for candidata: String in candidatas:
		for nombre: String in animaciones.get_animation_list():
			if nombre.to_lower().contains(candidata):
				return nombre
	return ""


func _buscar_animaciones(nodo: Node) -> AnimationPlayer:
	if nodo is AnimationPlayer:
		return nodo
	for hijo in nodo.get_children():
		var encontrado := _buscar_animaciones(hijo)
		if encontrado != null:
			return encontrado
	return null


# --- construcción ---------------------------------------------------------------------------

func _ojos(cabeza: Node3D, c: Dictionary) -> void:
	for lado: int in [1, -1]:
		_pieza(cabeza, _esfera(1.0), Vector3(0.055 * lado, 0.185, -0.131), Color(0.06, 0.04, 0.1), Vector3.ZERO, Vector3(0.034, 0.046, 0.014), false, true)
		_pieza(cabeza, _esfera(1.0), Vector3(0.055 * lado, 0.18, -0.142), c["ojos"], Vector3.ZERO, Vector3(0.021, 0.03, 0.008), false, true)
		_pieza(cabeza, _esfera(1.0), Vector3(0.049 * lado + 0.006, 0.194, -0.148), Color(1, 1, 1), Vector3.ZERO, Vector3(0.008, 0.008, 0.004), false, true)
		_pieza(cabeza, _caja(Vector3(0.07, 0.015, 0.014)), Vector3(0.058 * lado, 0.238, -0.134), c["pelo"], Vector3(0, 0, -14.0 * lado), Vector3.ONE, false, true)


func _pelo(cabeza: Node3D, c: Dictionary) -> void:
	var color: Color = c["pelo"]
	var punta: Color = c["punta"]
	var casco := _pieza(cabeza, _esfera(0.158, true), Vector3(0, 0.185, 0.012), color, Vector3(18, 0, 0), Vector3(1.0, 1.0, 1.06))
	casco.name = "Casco"
	var mechones: Array = MECHONES_PUNTAS if def.get("pelo") == "puntas" else MECHONES_COLETA
	for m: Array in mechones:
		var base: Variant = m[3] if m.size() > 3 else null
		_mechon(cabeza, m[0], m[1], m[2], color, punta, base)
	if def.get("pelo") == "coleta":
		_pieza(cabeza, _cilindro(0.05, 0.05, 0.05), Vector3(0, 0.3, 0.12), c["cinta"], Vector3(70, 0, 0))
		coleta = Node3D.new()
		coleta.name = "Coleta"
		coleta.position = Vector3(0, 0.3, 0.13)
		cabeza.add_child(coleta)
		var direccion := Vector3(0, -0.45, 1.0).normalized()
		var tramos := [[0.12, 0.22, 0.08], [0.27, 0.2, 0.065], [0.4, 0.18, 0.05]]
		for tramo: Array in tramos:
			_mechon(coleta, direccion, tramo[1], tramo[2], color, punta, direccion * float(tramo[0]) - direccion * float(tramo[1]) * 0.5)
	if def.get("accesorio") == "cinta":
		var aro := TorusMesh.new()
		aro.inner_radius = 0.148
		aro.outer_radius = 0.172
		aro.rings = 24
		aro.ring_segments = 8
		_pieza(cabeza, aro, Vector3(0, 0.23, 0.0), c["cinta"], Vector3(12, 0, 0), Vector3(1.0, 2.0, 1.04))
		for i in 2:
			var ancla := Node3D.new()
			ancla.position = Vector3(0.02 * (1 - 2 * i), 0.215, 0.16)
			cabeza.add_child(ancla)
			_pieza(ancla, _caja(Vector3(0.035, 0.008, 0.3)), Vector3(0, 0, 0.15), c["cinta"], Vector3.ZERO, Vector3.ONE, false)
			cintas.append(ancla)


func _mechon(padre: Node3D, direccion: Vector3, largo: float, radio: float, color: Color, punta: Color, base: Variant) -> void:
	var dir := direccion.normalized()
	var inicio: Vector3 = base if base != null else Vector3(0, 0.18, 0) + dir * 0.09
	var m := MeshInstance3D.new()
	m.mesh = _cono(radio, largo)
	m.basis = Basis(Quaternion(Vector3.UP, dir))
	m.position = inicio + dir * largo * 0.5
	var mat := ShaderMaterial.new()
	mat.shader = TOON
	mat.set_shader_parameter("color_base", color)
	mat.set_shader_parameter("color_punta", punta)
	mat.set_shader_parameter("punta_desde", largo * 0.02)
	mat.set_shader_parameter("punta_hasta", largo * 0.5)
	mat.next_pass = _contorno
	m.material_override = mat
	padre.add_child(m)


func _crear_aura(c: Dictionary) -> void:
	_aura_mat = ShaderMaterial.new()
	_aura_mat.shader = ENERGIA
	_aura_mat.set_shader_parameter("color", c["ki"])
	_aura_mat.set_shader_parameter("color_nucleo", c["ki"])
	_aura_mat.set_shader_parameter("intensidad", 1.1)
	_aura_mat.set_shader_parameter("centro", 0.04)
	_aura_mat.set_shader_parameter("poder_borde", 2.2)
	_aura_mat.set_shader_parameter("bandas", 5.0)
	_aura_mat.set_shader_parameter("velocidad", 3.0)
	_aura_mat.set_shader_parameter("opacidad", 0.0)
	aura = MeshInstance3D.new()
	var capsula := CapsuleMesh.new()
	capsula.radius = 0.75
	capsula.height = 2.7
	aura.mesh = capsula
	aura.material_override = _aura_mat
	aura.position = Vector3(0, -0.05, 0)
	aura.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	aura.visible = false
	add_child(aura)

	var mat_bola := ShaderMaterial.new()
	mat_bola.shader = ENERGIA
	mat_bola.set_shader_parameter("color", c["ki"])
	mat_bola.set_shader_parameter("color_nucleo", c["ki_nucleo"])
	mat_bola.set_shader_parameter("intensidad", 1.7)
	bola = MeshInstance3D.new()
	bola.mesh = _esfera(0.25)
	bola.material_override = mat_bola
	bola.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	bola.visible = false
	add_child(bola)


func _articulacion(nombre: String, padre: Node3D, posicion: Vector3) -> Node3D:
	var n := Node3D.new()
	n.name = nombre
	n.position = posicion
	padre.add_child(n)
	articulaciones[nombre] = n
	return n


func _pieza(padre: Node3D, malla: Mesh, posicion: Vector3, color: Color, rotacion := Vector3.ZERO,
		escala := Vector3.ONE, contorno := true, plano := false) -> MeshInstance3D:
	var m := MeshInstance3D.new()
	m.mesh = malla
	m.position = posicion
	m.rotation_degrees = rotacion
	m.scale = escala
	m.material_override = _material(color, contorno, plano)
	padre.add_child(m)
	return m


func _material(color: Color, contorno: bool, plano: bool) -> Material:
	var clave := "%s_%s_%s" % [color.to_html(), contorno, plano]
	if _materiales.has(clave):
		return _materiales[clave]
	var mat: Material
	if plano:
		var estandar := StandardMaterial3D.new()
		estandar.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		estandar.albedo_color = color
		mat = estandar
	else:
		var toon := ShaderMaterial.new()
		toon.shader = TOON
		toon.set_shader_parameter("color_base", color)
		if contorno:
			toon.next_pass = _contorno
		mat = toon
	_materiales[clave] = mat
	return mat


static func _capsula(radio: float, alto: float) -> CapsuleMesh:
	var m := CapsuleMesh.new()
	m.radius = radio
	m.height = maxf(alto, radio * 2.0)
	m.radial_segments = 16
	m.rings = 4
	return m


static func _esfera(radio: float, semiesfera := false) -> SphereMesh:
	var m := SphereMesh.new()
	m.radius = radio
	m.height = radio * (1.0 if semiesfera else 2.0)
	m.is_hemisphere = semiesfera
	m.radial_segments = 20
	m.rings = 10
	return m


static func _cilindro(arriba: float, abajo: float, alto: float) -> CylinderMesh:
	var m := CylinderMesh.new()
	m.top_radius = arriba
	m.bottom_radius = abajo
	m.height = alto
	m.radial_segments = 16
	m.rings = 1
	return m


static func _cono(radio: float, alto: float) -> CylinderMesh:
	var m := CylinderMesh.new()
	m.top_radius = 0.0
	m.bottom_radius = radio
	m.height = alto
	m.radial_segments = 8
	m.rings = 1
	return m


static func _caja(tamano: Vector3) -> BoxMesh:
	var m := BoxMesh.new()
	m.size = tamano
	return m
