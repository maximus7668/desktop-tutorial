extends Node

## Pruebas del combate sin ventana:
##   godot --headless --path . res://tests/pruebas.tscn
## Cada prueba monta un combate con controles guionizados y lo avanza fotograma a fotograma.
## Es una escena (no un --script) para que existan los nodos globales Sonidos, Recursos y Partida.

const DT := 1.0 / 60.0

var _fallos: Array[String] = []
var _hechas := 0
var _actual := ""
var _completada := ""


func _ready() -> void:
	var pruebas := [
		"combo_completo_lanza_al_rival",
		"guardia_reduce_el_dano",
		"golpe_fuerte_rompe_la_guardia",
		"embestida_desde_lejos",
		"rafaga_de_ki_alcanza_y_cuesta_ki",
		"cargar_ki",
		"esquiva_a_tiempo_teletransporta_detras",
		"esquiva_sin_ki_no_contraataca",
		"super_rayo_impacta",
		"choque_de_rayos_gana_quien_mas_machaca",
		"ko_termina_el_combate",
		"tiempo_agotado_gana_quien_tiene_mas_vida",
		"lanzado_contra_una_roca_la_rompe",
		"cpu_contra_cpu_termina",
		"hud_y_camara_funcionan",
		"pantalla_principal_funciona",
	]
	for nombre: String in pruebas:
		_actual = nombre
		var antes := _fallos.size()
		await call(nombre)
		if _completada != nombre:
			_fallos.append("%s: se interrumpió por un error (mira el SCRIPT ERROR de arriba)" % nombre)
		_hechas += 1
		print(("  ok     " if _fallos.size() == antes else "  FALLO  ") + nombre)
		for hijo in get_children():
			hijo.free()
		Sonidos.parar_todo()
	print("\n%d pruebas, %d fallos" % [_hechas, _fallos.size()])
	for fallo: String in _fallos:
		print("  - " + fallo)
	get_tree().quit(1 if not _fallos.is_empty() else 0)


# --- utilidades ----------------------------------------------------------------------------------

func listo() -> void:
	_completada = _actual


func comprobar(condicion: bool, mensaje: String) -> void:
	if not condicion:
		_fallos.append("%s: %s" % [_actual, mensaje])


func combate(guion_a: Callable, guion_b: Callable, opciones := {}) -> Combate:
	var c := Combate.new()
	add_child(c)
	var ajustes := {"sin_presentacion": true, "camara": false, "hud": false, "sombras": false}
	ajustes.merge(opciones, true)
	c.preparar("ren", "yuki", ControlGuion.new(guion_a), ControlGuion.new(guion_b), ajustes)
	c.set_physics_process(false)
	return c


func colocar(c: Combate, distancia: float, altura := 5.0) -> void:
	var a := c.luchadores[0]
	var b := c.luchadores[1]
	# Centrados: en un radio de 22 m alrededor del centro no hay rocas.
	a.global_position = Vector3(0, altura, distancia * 0.5)
	b.global_position = Vector3(0, altura, -distancia * 0.5)
	a.vel = Vector3.ZERO
	b.vel = Vector3.ZERO
	a.mirar_al_rival()
	b.mirar_al_rival()


func avanzar(c: Combate, segundos: float) -> void:
	for i in int(segundos * 60.0):
		c.paso(DT)


func quieto(_i: Intencion, _yo: Luchador, _f: int) -> void:
	pass


static func pulsar_en(fotogramas: Array, accion: String) -> Callable:
	return func(i: Intencion, _yo: Luchador, f: int) -> void:
		if f in fotogramas:
			i.set(accion, true)


# --- pruebas ------------------------------------------------------------------------------------

func combo_completo_lanza_al_rival() -> void:
	var c := combate(pulsar_en([0, 10, 20, 30, 40], "golpe_pulsado"), quieto)
	colocar(c, 1.8)
	var b := c.luchadores[1]
	avanzar(c, 1.2)
	var a := c.luchadores[0]
	comprobar(a.golpes_conectados == 5, "conectó %d golpes de 5" % a.golpes_conectados)
	var perdida := b.vida_max - b.vida
	comprobar(perdida > 250.0 and perdida < 420.0, "daño del combo fuera de rango: %.0f" % perdida)
	comprobar(b.estado in [Luchador.Estado.LANZADO, Luchador.Estado.RECUPERACION], "el remate no lanzó al rival (estado %s)" % Luchador.Estado.keys()[b.estado])
	comprobar(c.combos[0] >= 5 or c.combo_t[0] < 1.2, "el contador de combo no subió")
	listo()


func guardia_reduce_el_dano() -> void:
	var guardar := func(i: Intencion, _yo: Luchador, _f: int) -> void: i.guardia = true
	var c := combate(pulsar_en([0, 25, 50], "golpe_pulsado"), guardar)
	colocar(c, 1.8)
	avanzar(c, 1.5)
	var b := c.luchadores[1]
	var perdida := b.vida_max - b.vida
	comprobar(perdida > 0.0 and perdida < 30.0, "con guardia perdió %.1f" % perdida)
	comprobar(c.luchadores[0].ultimo_resultado == "bloqueado", "resultado: %s" % c.luchadores[0].ultimo_resultado)
	listo()


func golpe_fuerte_rompe_la_guardia() -> void:
	var cargar_golpe := func(i: Intencion, _yo: Luchador, f: int) -> void:
		i.golpe_pulsado = f == 0
		i.golpe = f < 40
	var guardar := func(i: Intencion, _yo: Luchador, _f: int) -> void: i.guardia = true
	var c := combate(cargar_golpe, guardar)
	colocar(c, 1.8)
	avanzar(c, 1.2)
	comprobar(c.luchadores[0].ultimo_resultado == "guardia_rota", "resultado: %s" % c.luchadores[0].ultimo_resultado)
	comprobar(c.luchadores[1].estado == Luchador.Estado.ATURDIDO, "el rival no quedó aturdido")
	listo()


func embestida_desde_lejos() -> void:
	var c := combate(pulsar_en([0], "golpe_pulsado"), quieto)
	colocar(c, 18.0)
	avanzar(c, 1.0)
	comprobar(c.luchadores[0].golpes_conectados >= 1, "la embestida no llegó a golpear")
	comprobar(c.luchadores[1].vida < c.luchadores[1].vida_max, "el rival no recibió daño")
	listo()


func rafaga_de_ki_alcanza_y_cuesta_ki() -> void:
	var c := combate(pulsar_en([0], "ki_pulsado"), quieto)
	colocar(c, 15.0)
	var a := c.luchadores[0]
	var b := c.luchadores[1]
	avanzar(c, 1.0)
	comprobar(is_equal_approx(a.ki, 200.0 - Luchador.COSTE_RAFAGA), "ki del que dispara: %.1f" % a.ki)
	comprobar(b.vida < b.vida_max, "la ráfaga no hizo daño")
	comprobar(c.rafagas.is_empty(), "la ráfaga sigue viva tras impactar")
	listo()


func cargar_ki() -> void:
	var cargar := func(i: Intencion, _yo: Luchador, _f: int) -> void: i.cargar = true
	var c := combate(cargar, quieto)
	colocar(c, 20.0)
	avanzar(c, 1.0)
	var ki := c.luchadores[0].ki
	comprobar(ki > 300.0 and ki < 330.0, "tras 1 s cargando: %.1f" % ki)
	avanzar(c, 3.0)
	comprobar(is_equal_approx(c.luchadores[0].ki, Luchador.KI_MAX), "no llega al máximo: %.1f" % c.luchadores[0].ki)
	comprobar(c.luchadores[0].estado == Luchador.Estado.LIBRE, "no deja de cargar al llenarse")
	listo()


func esquiva_a_tiempo_teletransporta_detras() -> void:
	var c := combate(pulsar_en([0], "golpe_pulsado"), pulsar_en([2], "impulso_pulsado"))
	colocar(c, 1.8)
	var a := c.luchadores[0]
	var b := c.luchadores[1]
	var b_antes := b.global_position
	avanzar(c, 0.25)
	comprobar(b.vida == b.vida_max, "el que esquiva recibió daño")
	comprobar(a.estado == Luchador.Estado.ATURDIDO, "el atacante no quedó aturdido (estado %s)" % Luchador.Estado.keys()[a.estado])
	comprobar(is_equal_approx(b.ki, 200.0 - Luchador.COSTE_ESQUIVA), "ki tras esquivar: %.1f" % b.ki)
	comprobar(b.global_position.distance_to(b_antes) > 2.0, "no se teletransportó")
	listo()


func esquiva_sin_ki_no_contraataca() -> void:
	var c := combate(pulsar_en([0], "golpe_pulsado"), pulsar_en([2], "impulso_pulsado"))
	colocar(c, 1.8)
	c.luchadores[1].ki = 10.0
	avanzar(c, 0.25)
	comprobar(c.luchadores[0].estado != Luchador.Estado.ATURDIDO, "contraatacó sin ki")
	listo()


func super_rayo_impacta() -> void:
	var c := combate(pulsar_en([0], "super_pulsado"), quieto)
	colocar(c, 20.0)
	var a := c.luchadores[0]
	var b := c.luchadores[1]
	avanzar(c, 0.1)
	comprobar(a.estado == Luchador.Estado.SUPER_CARGA, "no empezó a cargar el súper")
	comprobar(is_equal_approx(a.ki, 0.0), "el súper no gastó 2 barras: %.1f" % a.ki)
	avanzar(c, 2.5)
	var perdida := b.vida_max - b.vida
	comprobar(perdida > 600.0, "el rayo hizo poco daño: %.0f" % perdida)
	comprobar(not c.rayos.is_empty() or perdida > 0.0, "no se creó el rayo")
	listo()


func choque_de_rayos_gana_quien_mas_machaca() -> void:
	var machaca_rapido := func(i: Intencion, yo: Luchador, f: int) -> void:
		i.super_pulsado = f == 0
		if yo.estado == Luchador.Estado.CHOQUE and f % 4 == 0:
			i.golpe_pulsado = true
	var machaca_lento := func(i: Intencion, yo: Luchador, f: int) -> void:
		i.super_pulsado = f == 0
		if yo.estado == Luchador.Estado.CHOQUE and f % 12 == 0:
			i.golpe_pulsado = true
	var c := combate(machaca_rapido, machaca_lento)
	colocar(c, 30.0)
	var hubo_choque := false
	for i in 60 * 8:
		c.paso(DT)
		if not c.choque.is_empty():
			hubo_choque = true
	var a := c.luchadores[0]
	var b := c.luchadores[1]
	comprobar(hubo_choque, "los rayos no chocaron")
	comprobar(b.vida_max - b.vida > 600.0, "el perdedor apenas recibió daño: %.0f" % (b.vida_max - b.vida))
	comprobar(a.vida == a.vida_max, "el ganador recibió daño: %.0f" % (a.vida_max - a.vida))
	listo()


func ko_termina_el_combate() -> void:
	var c := combate(pulsar_en([0, 10, 20, 30, 40], "golpe_pulsado"), quieto)
	colocar(c, 1.8)
	c.luchadores[1].vida = 60.0
	var resultado := {"ganador": null, "emitido": false}
	c.terminado.connect(func(g: Luchador) -> void:
		resultado["ganador"] = g
		resultado["emitido"] = true)
	avanzar(c, 6.0)
	comprobar(c.luchadores[1].estado == Luchador.Estado.KO, "el rival no está K.O.")
	comprobar(resultado["emitido"], "no se emitió 'terminado'")
	comprobar(resultado["ganador"] == c.luchadores[0], "ganador equivocado")
	comprobar(c.resultado == "ko", "resultado: %s" % c.resultado)
	comprobar(c.luchadores[0].estado == Luchador.Estado.VICTORIA, "el ganador no celebra")
	listo()


func tiempo_agotado_gana_quien_tiene_mas_vida() -> void:
	var c := combate(quieto, quieto, {"tiempo": 1.0})
	colocar(c, 10.0)
	c.luchadores[0].vida -= 100.0
	avanzar(c, 5.0)
	comprobar(c.resultado == "tiempo", "resultado: %s" % c.resultado)
	comprobar(c.ganador == c.luchadores[1], "ganador equivocado")
	comprobar(c.fase == "fin", "fase: %s" % c.fase)
	listo()


func lanzado_contra_una_roca_la_rompe() -> void:
	var c := combate(quieto, quieto)
	var roca: Dictionary = c.arena.rocas[0]
	var base: Vector3 = roca["pos"]
	var b := c.luchadores[1]
	var fuera := Vector3(base.x, 3.0, base.z) + Vector3(1, 0, 0) * (float(roca["radio"]) + 6.0)
	b.global_position = fuera
	c.luchadores[0].global_position = fuera + Vector3(8, 0, 0)
	var vivas := c.arena.rocas_vivas()
	b.lanzar((Vector3(base.x, 3.0, base.z) - fuera).normalized() * 40.0)
	avanzar(c, 1.0)
	comprobar(c.arena.rocas_vivas() == vivas - 1, "la roca no se rompió")
	comprobar(b.vida < b.vida_max, "el choque no hizo daño")
	listo()


func cpu_contra_cpu_termina() -> void:
	var c := Combate.new()
	add_child(c)
	c.preparar("ren", "yuki", ControlCPU.new("dificil", 11), ControlCPU.new("dificil", 22), {"sin_presentacion": true, "camara": false, "hud": false, "tiempo": 90.0, "sombras": false})
	c.set_physics_process(false)
	var emitido := [false]
	c.terminado.connect(func(_g: Luchador) -> void: emitido[0] = true)
	var segundos := 0.0
	while not emitido[0] and segundos < 100.0:
		c.paso(DT)
		segundos += DT
	var a := c.luchadores[0]
	var b := c.luchadores[1]
	comprobar(emitido[0], "el combate no terminó")
	comprobar(a.vida < a.vida_max and b.vida < b.vida_max, "algún luchador no recibió daño")
	comprobar(a.golpes_conectados + b.golpes_conectados > 10, "pocos golpes: %d" % (a.golpes_conectados + b.golpes_conectados))
	print("         CPU contra CPU: %.0f s, %s, vida %.0f / %.0f, golpes %d / %d" % [segundos, c.resultado, a.vida, b.vida, a.golpes_conectados, b.golpes_conectados])
	listo()


func hud_y_camara_funcionan() -> void:
	var c := Combate.new()
	add_child(c)
	c.preparar("yuki", "ren", ControlCPU.new("normal", 3), ControlCPU.new("normal", 4), {"tiempo": 20.0, "sombras": false})
	c.set_physics_process(false)
	avanzar(c, 6.0)
	comprobar(c.hud != null and c.camara != null, "faltan HUD o cámara")
	comprobar(c.fase == "pelea", "fase: %s" % c.fase)
	listo()


func pantalla_principal_funciona() -> void:
	var escena: PackedScene = load("res://escenas/principal.tscn")
	var principal := escena.instantiate()
	principal.name = "Principal"
	add_child(principal)
	for i in 30:
		await get_tree().process_frame
	comprobar(principal.pantalla == "titulo", "no arrancó en el título")
	principal.call("_seleccionar")
	await get_tree().process_frame
	principal.call("_empezar_combate")
	for i in 20:
		await get_tree().process_frame
	comprobar(principal.pantalla == "combate", "no empezó el combate")
	comprobar(principal.combate != null and principal.combate.luchadores[0].control is ControlJugador, "el jugador no controla al luchador 1")
	principal.call("_pausar", true)
	comprobar(principal.combate.pausado, "la pausa no detiene el combate")
	principal.call("_pausar", false)
	listo()
