class_name Poses
extends RefCounted

## Poses del cuerpo provisional, en grados por articulación.
## Brazos y piernas cuelgan hacia abajo: x positivo los lleva hacia delante y arriba.
## Torso y cabeza apuntan hacia arriba: x negativo inclina hacia delante.
## Hombro derecho: z positivo abre el brazo hacia fuera (en el izquierdo, z negativo).

const ARTICULACIONES := [
	"pelvis", "torso", "cabeza",
	"hombro_d", "codo_d", "hombro_i", "codo_i",
	"cadera_d", "rodilla_d", "cadera_i", "rodilla_i",
]

const BASE := {
	"pelvis": Vector3.ZERO,
	"torso": Vector3(-6, 0, 0),
	"cabeza": Vector3(4, 0, 0),
	"hombro_d": Vector3(38, 0, 14), "codo_d": Vector3(92, 0, 0),
	"hombro_i": Vector3(32, 0, -14), "codo_i": Vector3(98, 0, 0),
	"cadera_d": Vector3(22, 0, 4), "rodilla_d": Vector3(-38, 0, 0),
	"cadera_i": Vector3(-4, 0, -4), "rodilla_i": Vector3(-18, 0, 0),
}

const CAMBIOS := {
	"golpe_d": {
		"torso": Vector3(-10, 28, 0),
		"hombro_d": Vector3(90, 0, 6), "codo_d": Vector3(4, 0, 0),
		"hombro_i": Vector3(30, 0, -18), "codo_i": Vector3(105, 0, 0),
	},
	"golpe_i": {
		"torso": Vector3(-10, -28, 0),
		"hombro_i": Vector3(90, 0, -6), "codo_i": Vector3(4, 0, 0),
		"hombro_d": Vector3(30, 0, 18), "codo_d": Vector3(105, 0, 0),
	},
	"patada_d": {
		"torso": Vector3(14, 0, 6),
		"cadera_d": Vector3(100, 0, 0), "rodilla_d": Vector3(-6, 0, 0),
		"cadera_i": Vector3(-10, 0, -6), "rodilla_i": Vector3(-25, 0, 0),
		"hombro_d": Vector3(20, 0, 50), "codo_d": Vector3(40, 0, 0),
		"hombro_i": Vector3(25, 0, -45), "codo_i": Vector3(50, 0, 0),
	},
	"patada_i": {
		"torso": Vector3(14, 0, -6),
		"cadera_i": Vector3(100, 0, 0), "rodilla_i": Vector3(-6, 0, 0),
		"cadera_d": Vector3(-10, 0, 6), "rodilla_d": Vector3(-25, 0, 0),
		"hombro_d": Vector3(25, 0, 45), "codo_d": Vector3(50, 0, 0),
		"hombro_i": Vector3(20, 0, -50), "codo_i": Vector3(40, 0, 0),
	},
	"remate_prep": {
		"torso": Vector3(12, 0, 0), "cabeza": Vector3(10, 0, 0),
		"hombro_d": Vector3(175, 0, -8), "codo_d": Vector3(20, 0, 0),
		"hombro_i": Vector3(175, 0, 8), "codo_i": Vector3(20, 0, 0),
	},
	"remate": {
		"torso": Vector3(-38, 0, 0),
		"hombro_d": Vector3(55, 0, -6), "codo_d": Vector3(12, 0, 0),
		"hombro_i": Vector3(55, 0, 6), "codo_i": Vector3(12, 0, 0),
		"cadera_d": Vector3(30, 0, 4), "rodilla_d": Vector3(-60, 0, 0),
		"cadera_i": Vector3(10, 0, -4), "rodilla_i": Vector3(-40, 0, 0),
	},
	"fuerte_prep": {
		"torso": Vector3(-4, -55, 0),
		"hombro_d": Vector3(-35, 0, 30), "codo_d": Vector3(70, 0, 0),
		"hombro_i": Vector3(60, 0, -10), "codo_i": Vector3(60, 0, 0),
	},
	"fuerte": {
		"torso": Vector3(-22, 50, 0),
		"hombro_d": Vector3(88, 0, 0), "codo_d": Vector3(0, 0, 0),
		"hombro_i": Vector3(10, 0, -40), "codo_i": Vector3(40, 0, 0),
		"cadera_d": Vector3(-15, 0, 4), "rodilla_d": Vector3(-20, 0, 0),
		"cadera_i": Vector3(35, 0, -4), "rodilla_i": Vector3(-50, 0, 0),
	},
	"rafaga_d": {
		"torso": Vector3(-4, 22, 0),
		"hombro_d": Vector3(90, 0, 2), "codo_d": Vector3(0, 0, 0),
		"hombro_i": Vector3(40, 0, -20), "codo_i": Vector3(80, 0, 0),
	},
	"rafaga_i": {
		"torso": Vector3(-4, -22, 0),
		"hombro_i": Vector3(90, 0, -2), "codo_i": Vector3(0, 0, 0),
		"hombro_d": Vector3(40, 0, 20), "codo_d": Vector3(80, 0, 0),
	},
	"cargar": {
		"torso": Vector3(14, 0, 0), "cabeza": Vector3(22, 0, 0),
		"hombro_d": Vector3(12, 0, 38), "codo_d": Vector3(35, 0, 0),
		"hombro_i": Vector3(12, 0, -38), "codo_i": Vector3(35, 0, 0),
		"cadera_d": Vector3(4, 0, 14), "rodilla_d": Vector3(-12, 0, 0),
		"cadera_i": Vector3(4, 0, -14), "rodilla_i": Vector3(-12, 0, 0),
	},
	"guardia": {
		"torso": Vector3(-16, 0, 0), "cabeza": Vector3(-10, 0, 0),
		"hombro_d": Vector3(78, 0, -28), "codo_d": Vector3(112, 0, 0),
		"hombro_i": Vector3(78, 0, 28), "codo_i": Vector3(112, 0, 0),
		"cadera_d": Vector3(30, 0, 0), "rodilla_d": Vector3(-55, 0, 0),
		"cadera_i": Vector3(10, 0, 0), "rodilla_i": Vector3(-35, 0, 0),
	},
	"paso": {
		"torso": Vector3(-20, 0, 0),
		"hombro_d": Vector3(-35, 0, 12), "codo_d": Vector3(20, 0, 0),
		"hombro_i": Vector3(-35, 0, -12), "codo_i": Vector3(20, 0, 0),
		"cadera_d": Vector3(-15, 0, 4), "rodilla_d": Vector3(-30, 0, 0),
		"cadera_i": Vector3(-25, 0, -4), "rodilla_i": Vector3(-20, 0, 0),
	},
	"correr": {
		"torso": Vector3(-30, 0, 0), "cabeza": Vector3(20, 0, 0),
		"hombro_d": Vector3(-20, 0, 15), "codo_d": Vector3(15, 0, 0),
		"hombro_i": Vector3(-20, 0, -15), "codo_i": Vector3(15, 0, 0),
		"cadera_d": Vector3(-20, 0, 4), "rodilla_d": Vector3(-25, 0, 0),
		"cadera_i": Vector3(-28, 0, -4), "rodilla_i": Vector3(-15, 0, 0),
	},
	"embestida": {
		"torso": Vector3(-30, 15, 0), "cabeza": Vector3(15, 0, 0),
		"hombro_d": Vector3(60, 0, 10), "codo_d": Vector3(110, 0, 0),
		"hombro_i": Vector3(-20, 0, -15), "codo_i": Vector3(20, 0, 0),
		"cadera_d": Vector3(-20, 0, 4), "rodilla_d": Vector3(-25, 0, 0),
		"cadera_i": Vector3(-28, 0, -4), "rodilla_i": Vector3(-15, 0, 0),
	},
	"super_carga": {
		"torso": Vector3(10, 0, 0), "cabeza": Vector3(18, 0, 0),
		"hombro_d": Vector3(165, 0, -12), "codo_d": Vector3(25, 0, 0),
		"hombro_i": Vector3(165, 0, 12), "codo_i": Vector3(25, 0, 0),
		"cadera_d": Vector3(8, 0, 10), "rodilla_d": Vector3(-20, 0, 0),
		"cadera_i": Vector3(8, 0, -10), "rodilla_i": Vector3(-20, 0, 0),
	},
	"super_rayo": {
		"torso": Vector3(-12, 0, 0),
		"hombro_d": Vector3(88, 0, -10), "codo_d": Vector3(0, 0, 0),
		"hombro_i": Vector3(88, 0, 10), "codo_i": Vector3(0, 0, 0),
		"cadera_d": Vector3(25, 0, 6), "rodilla_d": Vector3(-40, 0, 0),
		"cadera_i": Vector3(-20, 0, -6), "rodilla_i": Vector3(-10, 0, 0),
	},
	"aturdido": {
		"torso": Vector3(28, 0, 0), "cabeza": Vector3(24, 0, 0),
		"hombro_d": Vector3(-15, 0, 42), "codo_d": Vector3(30, 0, 0),
		"hombro_i": Vector3(-15, 0, -42), "codo_i": Vector3(30, 0, 0),
		"cadera_d": Vector3(-8, 0, 6), "rodilla_d": Vector3(-30, 0, 0),
		"cadera_i": Vector3(14, 0, -6), "rodilla_i": Vector3(-40, 0, 0),
	},
	"lanzado": {
		"torso": Vector3(35, 0, 0), "cabeza": Vector3(30, 0, 0),
		"hombro_d": Vector3(-40, 0, 70), "codo_d": Vector3(20, 0, 0),
		"hombro_i": Vector3(-40, 0, -70), "codo_i": Vector3(20, 0, 0),
		"cadera_d": Vector3(-20, 0, 18), "rodilla_d": Vector3(-20, 0, 0),
		"cadera_i": Vector3(-20, 0, -18), "rodilla_i": Vector3(-20, 0, 0),
	},
	"recuperacion": {
		"torso": Vector3(-40, 0, 0), "cabeza": Vector3(-10, 0, 0),
		"hombro_d": Vector3(60, 0, 10), "codo_d": Vector3(100, 0, 0),
		"hombro_i": Vector3(60, 0, -10), "codo_i": Vector3(100, 0, 0),
		"cadera_d": Vector3(80, 0, 0), "rodilla_d": Vector3(-110, 0, 0),
		"cadera_i": Vector3(80, 0, 0), "rodilla_i": Vector3(-110, 0, 0),
	},
	"ko": {
		"torso": Vector3(10, 0, 0), "cabeza": Vector3(20, 0, 0),
		"hombro_d": Vector3(0, 0, 25), "codo_d": Vector3(10, 0, 0),
		"hombro_i": Vector3(0, 0, -25), "codo_i": Vector3(10, 0, 0),
		"cadera_d": Vector3(0, 0, 8), "rodilla_d": Vector3(-10, 0, 0),
		"cadera_i": Vector3(0, 0, -8), "rodilla_i": Vector3(-10, 0, 0),
	},
	"victoria": {
		"torso": Vector3(6, 0, 0), "cabeza": Vector3(10, 0, 0),
		"hombro_d": Vector3(172, 0, 8), "codo_d": Vector3(0, 0, 0),
		"hombro_i": Vector3(22, 0, -24), "codo_i": Vector3(70, 0, 0),
		"cadera_d": Vector3(6, 0, 4), "rodilla_d": Vector3(-10, 0, 0),
		"cadera_i": Vector3(-4, 0, -4), "rodilla_i": Vector3(-12, 0, 0),
	},
	"presentacion": {
		"torso": Vector3(4, 0, 0), "cabeza": Vector3(6, 0, 0),
		"hombro_d": Vector3(60, 0, -30), "codo_d": Vector3(100, 0, 0),
		"hombro_i": Vector3(55, 0, 30), "codo_i": Vector3(105, 0, 0),
		"cadera_d": Vector3(6, 0, 4), "rodilla_d": Vector3(-8, 0, 0),
		"cadera_i": Vector3(-2, 0, -4), "rodilla_i": Vector3(-10, 0, 0),
	},
}

static var _cache: Dictionary = {}


static func obtener(nombre: String) -> Dictionary:
	if _cache.has(nombre):
		return _cache[nombre]
	var pose := BASE.duplicate()
	var cambios: Dictionary = CAMBIOS.get(nombre, {})
	for articulacion: String in cambios:
		pose[articulacion] = cambios[articulacion]
	_cache[nombre] = pose
	return pose


static func mezclar(a: Dictionary, b: Dictionary, k: float) -> Dictionary:
	var resultado := {}
	for articulacion: String in ARTICULACIONES:
		var va: Vector3 = a.get(articulacion, Vector3.ZERO)
		var vb: Vector3 = b.get(articulacion, Vector3.ZERO)
		resultado[articulacion] = va.lerp(vb, k)
	return resultado
