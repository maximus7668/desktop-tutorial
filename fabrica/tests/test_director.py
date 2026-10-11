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
