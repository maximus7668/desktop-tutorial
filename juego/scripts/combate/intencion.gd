class_name Intencion
extends RefCounted

## Lo que un luchador quiere hacer en este fotograma. La rellena el jugador (mando/teclado),
## la IA o un guion de pruebas: el luchador no distingue quién la manda.

var mover := Vector2.ZERO  # x: derecha (+) / izquierda (-); y: hacia el rival (+) / alejarse (-)
var altura := 0.0  # +1 subir, -1 bajar
var impulso := false
var impulso_pulsado := false
var golpe := false
var golpe_pulsado := false
var ki := false
var ki_pulsado := false
var guardia := false
var cargar := false
var super_pulsado := false


func limpiar() -> void:
	mover = Vector2.ZERO
	altura = 0.0
	impulso = false
	impulso_pulsado = false
	golpe = false
	golpe_pulsado = false
	ki = false
	ki_pulsado = false
	guardia = false
	cargar = false
	super_pulsado = false
