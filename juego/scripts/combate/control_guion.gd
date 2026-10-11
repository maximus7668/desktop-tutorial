class_name ControlGuion
extends RefCounted

## Control para pruebas: cada fotograma llama a una función que rellena la intención.
## Sin función, el luchador se queda quieto.

var funcion: Callable
var fotograma := 0


func _init(f: Callable = Callable()) -> void:
	funcion = f


func leer(i: Intencion, yo: Luchador, _dt: float) -> void:
	i.limpiar()
	if funcion.is_valid():
		funcion.call(i, yo, fotograma)
	fotograma += 1
