class_name ControlJugador
extends RefCounted

## Lee el teclado o el mando.


func leer(i: Intencion, _yo: Luchador, _dt: float) -> void:
	i.mover = Input.get_vector("izquierda", "derecha", "atras", "adelante")
	i.altura = Input.get_axis("bajar", "subir")
	i.impulso = Input.is_action_pressed("impulso")
	i.impulso_pulsado = Input.is_action_just_pressed("impulso")
	i.golpe = Input.is_action_pressed("golpe")
	i.golpe_pulsado = Input.is_action_just_pressed("golpe")
	i.ki = Input.is_action_pressed("ki")
	i.ki_pulsado = Input.is_action_just_pressed("ki")
	i.guardia = Input.is_action_pressed("guardia")
	i.cargar = Input.is_action_pressed("cargar")
	i.super_pulsado = Input.is_action_just_pressed("super")
