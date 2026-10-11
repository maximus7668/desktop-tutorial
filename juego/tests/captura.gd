extends Node

## Capturas para revisar el aspecto sin abrir el editor:
##   godot --path . --rendering-method gl_compatibility --fixed-fps 60 res://tests/captura.tscn -- <escenario> <segundos> <archivo.png>
## Escenarios: titulo, combate, cerca, rayo, choque, carga.

func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var escenario: String = args[0] if args.size() > 0 else "titulo"
	var segundos := float(args[1]) if args.size() > 1 else 2.0
	var archivo: String = args[2] if args.size() > 2 else "res://tests/capturas/%s.png" % escenario
	match escenario:
		"titulo":
			add_child((load("res://escenas/principal.tscn") as PackedScene).instantiate())
		_:
			_combate(escenario)
	for i in int(segundos * 60.0):
		await get_tree().physics_frame
	await get_tree().process_frame
	await get_tree().process_frame
	var imagen := get_viewport().get_texture().get_image()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(archivo.get_base_dir()))
	imagen.save_png(archivo)
	print("captura guardada: ", archivo)
	get_tree().quit(0)


func _combate(escenario: String) -> void:
	var c := Combate.new()
	add_child(c)
	var a: Variant
	var b: Variant
	match escenario:
		"combate":
			a = ControlCPU.new("dificil", 5)
			b = ControlCPU.new("dificil", 6)
		"rayo":
			a = ControlGuion.new(func(i: Intencion, _yo: Luchador, f: int) -> void: i.super_pulsado = f == 10)
			b = ControlGuion.new()
		"choque":
			a = ControlGuion.new(func(i: Intencion, yo: Luchador, f: int) -> void:
				i.super_pulsado = f == 10
				i.golpe_pulsado = yo.estado == Luchador.Estado.CHOQUE and f % 5 == 0)
			b = ControlGuion.new(func(i: Intencion, yo: Luchador, f: int) -> void:
				i.super_pulsado = f == 10
				i.golpe_pulsado = yo.estado == Luchador.Estado.CHOQUE and f % 6 == 0)
		"carga":
			a = ControlGuion.new(func(i: Intencion, _yo: Luchador, _f: int) -> void: i.cargar = true)
			b = ControlGuion.new()
		"cerca":
			a = ControlGuion.new(func(i: Intencion, _yo: Luchador, f: int) -> void: i.golpe_pulsado = f % 10 == 0 and f > 30)
			b = ControlGuion.new()
		_:
			a = ControlGuion.new()
			b = ControlGuion.new()
	c.preparar("ren", "yuki", a, b, {"sin_presentacion": escenario != "presentacion"})
	if escenario in ["rayo", "choque", "carga"]:
		c.luchadores[0].global_position = Vector3(0, 6, 12)
		c.luchadores[1].global_position = Vector3(0, 6, -12)
	if escenario == "cerca":
		c.luchadores[0].global_position = Vector3(0, 4, 1)
		c.luchadores[1].global_position = Vector3(0, 4, -1)
	for l: Luchador in c.luchadores:
		l.mirar_al_rival()
