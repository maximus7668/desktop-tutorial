extends Node

## Efectos de sonido. Si la fábrica ha entregado un sonido con el mismo id, suena ese;
## si no, uno sintetizado aquí mismo para que el juego nunca esté mudo.

const MEZCLA := 22050

var volumen_db := -8.0
var _sintetizados: Dictionary = {}
var _reproductores: Array[AudioStreamPlayer] = []
var _bucles: Dictionary = {}  # clave -> AudioStreamPlayer
var _siguiente := 0


func _ready() -> void:
	_generar()
	for i in 14:
		var reproductor := AudioStreamPlayer.new()
		add_child(reproductor)
		_reproductores.append(reproductor)


func tocar(id: String, volumen := 0.0, tono := 1.0) -> void:
	var stream := _stream(id)
	if stream == null or _reproductores.is_empty():
		return
	var reproductor := _reproductores[_siguiente]
	_siguiente = (_siguiente + 1) % _reproductores.size()
	reproductor.stream = stream
	reproductor.volume_db = volumen_db + volumen
	reproductor.pitch_scale = tono
	reproductor.play()


func voz(personaje: String, frase: String) -> void:
	var stream := Recursos.voz(personaje, frase)
	if stream == null:
		return
	var reproductor := _reproductores[_siguiente]
	_siguiente = (_siguiente + 1) % _reproductores.size()
	reproductor.stream = stream
	reproductor.volume_db = volumen_db + 4.0
	reproductor.pitch_scale = 1.0
	reproductor.play()


## Sonido continuo (cargar ki, rayo...). Llamarlo cada fotograma con activo = true/false.
func bucle(clave: String, id: String, activo: bool, volumen := 0.0) -> void:
	var reproductor: AudioStreamPlayer = _bucles.get(clave)
	if not activo:
		if reproductor and reproductor.playing:
			reproductor.stop()
		return
	if reproductor == null:
		reproductor = AudioStreamPlayer.new()
		add_child(reproductor)
		_bucles[clave] = reproductor
	if not reproductor.playing:
		reproductor.stream = _stream(id)
		reproductor.volume_db = volumen_db + volumen
		reproductor.play()


func parar_todo() -> void:
	for reproductor: AudioStreamPlayer in _bucles.values():
		reproductor.stop()


func _stream(id: String) -> AudioStream:
	var de_fabrica := Recursos.sonido(id)
	return de_fabrica if de_fabrica != null else _sintetizados.get(id)


func _generar() -> void:
	# duración, frecuencia inicial, final, ruido (0-1), caída, volumen
	_sintetizados["golpe"] = _sintetizar(0.14, 180.0, 60.0, 0.65, 26.0, 0.9)
	_sintetizados["golpe_fuerte"] = _sintetizar(0.38, 140.0, 38.0, 0.7, 9.0, 1.0)
	_sintetizados["bloqueo"] = _sintetizar(0.12, 900.0, 500.0, 0.45, 30.0, 0.6)
	_sintetizados["aire"] = _sintetizar(0.12, 500.0, 1500.0, 0.95, 18.0, 0.25)
	_sintetizados["rafaga"] = _sintetizar(0.22, 320.0, 1250.0, 0.35, 11.0, 0.5)
	_sintetizados["explosion"] = _sintetizar(0.9, 90.0, 30.0, 0.85, 3.6, 1.0)
	_sintetizados["impacto"] = _sintetizar(0.45, 70.0, 30.0, 0.8, 6.0, 1.0)
	_sintetizados["paso"] = _sintetizar(0.16, 900.0, 2400.0, 0.9, 16.0, 0.35)
	_sintetizados["teletransporte"] = _sintetizar(0.28, 2200.0, 500.0, 0.25, 9.0, 0.5)
	_sintetizados["super"] = _sintetizar(0.9, 110.0, 520.0, 0.35, 1.6, 0.7)
	_sintetizados["ko"] = _sintetizar(1.3, 120.0, 35.0, 0.6, 2.2, 1.0)
	_sintetizados["anuncio"] = _sintetizar(0.35, 660.0, 990.0, 0.05, 6.0, 0.4)
	_sintetizados["menu"] = _sintetizar(0.07, 880.0, 880.0, 0.0, 30.0, 0.3)
	_sintetizados["carga"] = _sintetizar(1.0, 75.0, 75.0, 0.55, 0.0, 0.45, true)
	_sintetizados["rayo"] = _sintetizar(1.0, 120.0, 120.0, 0.7, 0.0, 0.6, true)
	_sintetizados["choque"] = _sintetizar(1.0, 60.0, 60.0, 0.9, 0.0, 0.8, true)


func _sintetizar(duracion: float, f0: float, f1: float, ruido: float, caida: float, volumen: float, bucle_continuo := false) -> AudioStreamWAV:
	var n := int(duracion * MEZCLA)
	var datos := PackedByteArray()
	datos.resize(n * 2)
	var azar := RandomNumberGenerator.new()
	azar.seed = int(f0 * 1000.0 + duracion * 77.0)
	var fase := 0.0
	var filtrado := 0.0
	for i in n:
		var t := float(i) / MEZCLA
		var frecuencia := lerpf(f0, f1, t / duracion)
		fase += TAU * frecuencia / MEZCLA
		filtrado = lerpf(filtrado, azar.randf_range(-1.0, 1.0), 0.3)
		var envolvente := 1.0 if bucle_continuo else exp(-caida * t) * minf(1.0, t * 300.0)
		var valor := (sin(fase) * (1.0 - ruido) + filtrado * ruido * 1.6) * envolvente * volumen
		datos.encode_s16(i * 2, int(clampf(valor, -1.0, 1.0) * 32767.0))
	var onda := AudioStreamWAV.new()
	onda.format = AudioStreamWAV.FORMAT_16_BITS
	onda.mix_rate = MEZCLA
	onda.stereo = false
	onda.data = datos
	if bucle_continuo:
		onda.loop_mode = AudioStreamWAV.LOOP_FORWARD
		onda.loop_begin = 0
		onda.loop_end = n
	return onda
