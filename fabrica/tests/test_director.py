import json

from fabrica.agentes.elevenlabs import AgenteElevenLabs
from fabrica.diseno import ErrorDiseno
from fabrica.director import Director, ErrorOrden
from fabrica.registro import APROBADO, ERROR, ESPERANDO, PENDIENTE, SIN_AGENTE

from .util import MINIMO, ConProyecto, Grabador


class TestDirector(ConProyecto):
    def director(self, agente=None, **otros):
        return Director(self.carpeta, agentes={"simulado": agente or Grabador(), **otros})

    def completar(self, director):
        director.ejecutar()
        director.aprobar_todo()
        director.ejecutar()

    def test_primera_vuelta_se_para_en_lo_que_necesita_visto_bueno(self):
        d = self.director()
        informe = d.ejecutar()
        self.assertEqual(informe.hechas, ["ren/concepto", "ren/voz/grito", "sonido/impacto"])
        self.assertEqual(d.entrada("ren/concepto").estado, ESPERANDO)
        self.assertEqual(d.entrada("ren/voz/grito").estado, APROBADO)
        self.assertEqual(d.entrada("ren/modelo3d").estado, PENDIENTE)
        self.assertTrue((self.carpeta / d.entrada("ren/concepto").archivos[0]).is_file())

    def test_aprobar_desbloquea_lo_siguiente_y_exporta_completo(self):
        d = self.director()
        self.completar(d)
        self.assertTrue(all(d.entrada(t.id).estado == APROBADO for t in d.tareas))
        indice = json.loads(d.exportar().read_text(encoding="utf-8"))
        self.assertTrue(indice["completo"])
        self.assertEqual(indice["personajes"]["ren"]["modelo"], ["recursos/ren/rig/modelo_rig.gltf"])
        self.assertEqual(indice["personajes"]["ren"]["animaciones"]["golpe"], ["recursos/ren/animacion/golpe/golpe.json"])

    def test_parar_entre_tareas(self):
        d = self.director()
        self.assertTrue(d.ejecutar(seguir=lambda: False).detenido)
        self.assertEqual(d.entrada("ren/concepto").estado, PENDIENTE)
        respuestas = iter([True, False])
        informe = d.ejecutar(seguir=lambda: next(respuestas))
        self.assertEqual((informe.hechas, informe.detenido), (["ren/concepto"], True))

    def test_el_registro_sobrevive_entre_ejecuciones(self):
        self.director().ejecutar()
        otra_vez = self.director()
        self.assertEqual(otra_vez.entrada("ren/concepto").estado, ESPERANDO)
        self.assertEqual(otra_vez.ejecutar().hechas, [])

    def test_rechazar_rehace_con_el_motivo_y_reinicia_lo_que_dependia(self):
        agente = Grabador()
        d = self.director(agente)
        self.completar(d)
        afectadas = d.rechazar("ren/modelo3d", "más alto")
        self.assertEqual(afectadas, ["ren/animacion/golpe", "ren/limpieza", "ren/rig"])
        self.assertEqual(d.entrada("ren/rig").estado, PENDIENTE)
        self.assertEqual(d.entrada("ren/rig").archivos, [])

        agente.contextos.clear()
        d.ejecutar()
        self.assertEqual(agente.ids(), ["ren/modelo3d", "ren/limpieza", "ren/rig", "ren/animacion/golpe"])
        self.assertEqual(agente.contextos[0].motivo_rechazo, "más alto")
        self.assertEqual(agente.contextos[0].rechazos, 1)  # un pedido nuevo aunque repitas el motivo
        self.assertEqual(d.entrada("ren/modelo3d").motivo_rechazo, "")  # aprobado solo: ya se tuvo en cuenta

    def test_cambiar_el_diseno_rehace_solo_lo_afectado(self):
        self.completar(self.director())
        self.escribir(MINIMO.replace("Luchador de fuego", "Luchador de hielo"))
        d = self.director()
        self.assertEqual(d.entrada("ren/concepto").estado, PENDIENTE)
        self.assertEqual(d.entrada("ren/animacion/golpe").estado, PENDIENTE)
        self.assertEqual(d.entrada("ren/voz/grito").estado, APROBADO)
        self.assertEqual(d.entrada("sonido/impacto").estado, APROBADO)

    def test_animacion_nueva_y_descripcion_cambiada_a_la_vez(self):
        self.completar(self.director())
        nuevo = MINIMO.replace("Luchador de fuego", "Otro").replace('["golpe"]', '["golpe", "patada"]')
        self.escribir(nuevo)
        d = self.director()
        self.assertEqual(d.entrada("ren/animacion/patada").estado, PENDIENTE)

    def test_tarea_borrada_del_diseno_sale_del_registro(self):
        self.director().ejecutar()
        self.escribir(MINIMO.replace('[personajes.frases]\ngrito = "¡Ya!"', ""))
        d = self.director()
        self.assertNotIn("ren/voz/grito", d.registro.entradas)

    def test_un_fallo_no_para_al_resto_y_se_reintenta_hasta_el_maximo(self):
        agente = Grabador(falla_en={"sonido/impacto"})
        d = self.director(agente)
        informe = d.ejecutar()
        self.assertEqual(informe.errores, ["sonido/impacto"])
        self.assertIn("ren/voz/grito", informe.hechas)
        self.assertEqual(d.entrada("sonido/impacto").nota, "fallo provocado")
        d.ejecutar()
        d.ejecutar()  # intentos_max = 2: la tercera vez ya no lo intenta
        self.assertEqual(agente.ids().count("sonido/impacto"), 2)
        self.assertEqual(d.entrada("sonido/impacto").estado, ERROR)
        self.assertEqual(list(self.carpeta.rglob("*.tmp")), [])

    def test_si_falla_al_rehacer_se_conserva_lo_anterior_en_disco(self):
        agente = Grabador()
        d = self.director(agente)
        d.ejecutar()
        d.rechazar("ren/concepto", "más colores")
        agente.falla_en = {"ren/concepto"}
        d.ejecutar()
        self.assertTrue((self.carpeta / "recursos/ren/concepto/concepto.svg").is_file())

    def test_proveedor_sin_clave_queda_sin_agente_y_no_bloquea_lo_demas(self):
        self.escribir(MINIMO.replace("intentos_max = 2", 'intentos_max = 2\n\n[fabrica.proveedores]\nvoz = "elevenlabs"'))
        d = self.director(elevenlabs=AgenteElevenLabs(clave=""))
        informe = d.ejecutar()
        self.assertEqual(informe.sin_agente, ["ren/voz/grito"])
        self.assertEqual(d.entrada("ren/voz/grito").estado, SIN_AGENTE)
        self.assertIn("ELEVENLABS_API_KEY", d.entrada("ren/voz/grito").nota)
        self.assertIn("ren/concepto", informe.hechas)

    def test_proveedor_que_no_hace_ese_tipo(self):
        self.escribir(MINIMO.replace("intentos_max = 2", 'intentos_max = 2\n\n[fabrica.proveedores]\nconcepto = "elevenlabs"'))
        with self.assertRaisesRegex(ErrorDiseno, "no hace 'concepto'"):
            Director(self.carpeta)

    def test_proveedor_que_no_existe(self):
        self.escribir(MINIMO.replace("intentos_max = 2", 'intentos_max = 2\n\n[fabrica.proveedores]\nvoz = "eleven"'))
        with self.assertRaisesRegex(ErrorDiseno, "no existe ese proveedor"):
            Director(self.carpeta)

    def test_aprobar_por_grupo_y_errores_de_orden(self):
        d = self.director()
        d.ejecutar()
        self.assertEqual(d.aprobar(["ren"]), ["ren/concepto"])
        with self.assertRaisesRegex(ErrorOrden, "no espera tu visto bueno"):
            d.aprobar(["ren/voz/grito"])
        with self.assertRaisesRegex(ErrorOrden, "¿Querías decir 'ren/concepto'?"):
            d.aprobar(["ren/concepot"])
        with self.assertRaisesRegex(ErrorOrden, "Nada dentro de ren"):
            d.aprobar(["ren"])
        with self.assertRaisesRegex(ErrorOrden, "Solo se puede rechazar"):
            d.rechazar("ren/rig", "x")
        with self.assertRaisesRegex(ErrorOrden, "motivo"):
            d.rechazar("ren/concepto", "   ")

    def test_maximo_de_tareas_por_vuelta(self):
        d = self.director()
        informe = d.ejecutar(maximo=1)
        self.assertEqual(len(informe.hechas), 1)
        self.assertTrue(informe.limite_alcanzado)


class TestMontar(ConProyecto):
    def preparar_juego(self):
        juego = self.carpeta / "juego"
        juego.mkdir()
        (juego / "project.godot").write_text("config_version=5\n", encoding="utf-8")
        return juego

    def completar(self):
        d = Director(self.carpeta, agentes={"simulado": Grabador()})
        d.ejecutar()
        d.aprobar_todo()
        d.ejecutar()
        return d

    def test_sin_simulados_no_copia_relleno(self):
        d = self.completar()
        juego = self.preparar_juego()
        montaje = d.montar(juego)
        self.assertEqual(montaje.copiados, [])
        self.assertIn("ren/rig", montaje.omitidos)
        indice = json.loads((juego / "recursos_fabrica" / "indice.json").read_text(encoding="utf-8"))
        self.assertEqual(indice["personajes"]["ren"], {"nombre": "Ren"})
        self.assertEqual(indice["sonidos"], {})

    def test_con_simulados_copia_y_usa_rutas_de_godot(self):
        d = self.completar()
        juego = self.preparar_juego()
        d.montar(juego, incluir_simulados=True)
        indice = json.loads((juego / "recursos_fabrica" / "indice.json").read_text(encoding="utf-8"))
        modelo = indice["personajes"]["ren"]["modelo"][0]
        self.assertEqual(modelo, "res://recursos_fabrica/ren/rig/modelo_rig.gltf")
        self.assertTrue((juego / "recursos_fabrica" / "ren" / "rig" / "modelo_rig.gltf").is_file())
        self.assertEqual(indice["sonidos"]["impacto"], ["res://recursos_fabrica/sonido/impacto/impacto.wav"])
        self.assertEqual(list(indice["personajes"]["ren"]["voces"]), ["grito"])

    def test_rehace_la_carpeta_y_no_deja_restos(self):
        d = self.completar()
        juego = self.preparar_juego()
        d.montar(juego, incluir_simulados=True)
        sobrante = juego / "recursos_fabrica" / "viejo.txt"
        sobrante.write_text("x", encoding="utf-8")
        d.montar(juego, incluir_simulados=True)
        self.assertFalse(sobrante.exists())
        self.assertEqual(list(juego.glob(".recursos_fabrica.tmp")), [])

    def test_no_toca_una_carpeta_que_no_es_suya(self):
        d = self.completar()
        juego = self.preparar_juego()
        ajena = juego / "recursos_fabrica"
        ajena.mkdir()
        (ajena / "mio.txt").write_text("importante", encoding="utf-8")
        with self.assertRaisesRegex(ErrorOrden, "no lo creó la fábrica"):
            d.montar(juego)
        self.assertTrue((ajena / "mio.txt").exists())

    def test_exige_un_proyecto_de_godot(self):
        d = self.completar()
        with self.assertRaisesRegex(ErrorOrden, "project.godot"):
            d.montar(self.carpeta)
