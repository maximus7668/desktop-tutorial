extends Node

## Lo que la fábrica ha dejado en res://recursos_fabrica/ (con «python -m fabrica montar»).
## Si un recurso no está, el juego usa su versión provisional: nunca falla por faltar algo.

const INDICE := "res://recursos_fabrica/indice.json"

var indice: Dictionary = {}


func _ready() -> void:
	cargar_indice()


func cargar_indice() -> void:
	indice = {}
	if not FileAccess.file_exists(INDICE):
		return
	var datos: Variant = JSON.parse_string(FileAccess.get_file_as_string(INDICE))
	if datos is Dictionary:
		indice = datos
	else:
		push_warning("recursos_fabrica/indice.json no es un JSON válido; se usan los recursos provisionales.")


func modelo(personaje: String) -> PackedScene:
	var ruta := _primera(_personaje(personaje).get("modelo", []), [".glb", ".gltf", ".tscn", ".scn"])
	if ruta.is_empty() or not ResourceLoader.exists(ruta):
		return null
	var recurso := load(ruta)
	return recurso as PackedScene


func sonido(id: String) -> AudioStream:
	return _audio(indice.get("sonidos", {}).get(id, []))


func voz(personaje: String, frase: String) -> AudioStream:
	return _audio(_personaje(personaje).get("voces", {}).get(frase, []))


func musica(id: String) -> AudioStream:
	return _audio(indice.get("musica", {}).get(id, []))


func _personaje(id: String) -> Dictionary:
	var personajes: Dictionary = indice.get("personajes", {})
	return personajes.get(id, {})


func _audio(rutas: Array) -> AudioStream:
	var ruta := _primera(rutas, [".mp3", ".wav", ".ogg"])
	if ruta.is_empty() or not ResourceLoader.exists(ruta):
		return null
	return load(ruta) as AudioStream


func _primera(rutas: Array, extensiones: Array) -> String:
	for ruta: String in rutas:
		for extension: String in extensiones:
			if ruta.to_lower().ends_with(extension):
				return ruta
	return ""
