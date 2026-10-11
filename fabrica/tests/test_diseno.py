import tomllib
import unittest
from importlib import resources

from fabrica.diseno import ErrorDiseno, validar
from fabrica.plan import planificar

from .util import MINIMO


def diseno(texto: str = MINIMO):
    return validar(tomllib.loads(texto))


class TestDiseno(unittest.TestCase):
    def test_la_plantilla_es_valida(self):
        texto = resources.files("fabrica").joinpath("plantilla/juego.toml").read_text(encoding="utf-8")
        d = diseno(texto)
        self.assertEqual([p.id for p in d.personajes], ["ren", "yuki"])
        self.assertIn("tecnica_guren", d.personajes[0].animaciones)
        self.assertEqual(dict(d.personajes[0].frases)["tecnica"], "¡Guren... Bakuha!")
        self.assertEqual(set(d.proveedores.values()), {"simulado"})

    def test_textos_largos_quedan_en_una_linea(self):
        d = diseno(MINIMO.replace('"Luchador de fuego"', '"""\nLuchador\n  de fuego\n"""'))
        self.assertEqual(d.personajes[0].descripcion, "Luchador de fuego")

    def test_id_con_mayusculas(self):
        with self.assertRaisesRegex(ErrorDiseno, "no vale como id"):
            diseno(MINIMO.replace('id = "ren"', 'id = "Ren"'))

    def test_clave_mal_escrita_sugiere_la_buena(self):
        with self.assertRaisesRegex(ErrorDiseno, "¿Querías decir 'animaciones'?"):
            diseno(MINIMO.replace("animaciones =", "animacion ="))

    def test_tipo_desconocido_en_aprobar(self):
        with self.assertRaisesRegex(ErrorDiseno, "¿Querías decir 'concepto'?"):
            diseno(MINIMO.replace('aprobar = ["concepto"]', 'aprobar = ["conceptos"]'))

    def test_id_reservado(self):
        with self.assertRaisesRegex(ErrorDiseno, "reservado"):
            diseno(MINIMO.replace('id = "ren"', 'id = "sonido"'))

    def test_ids_repetidos(self):
        with self.assertRaisesRegex(ErrorDiseno, "repetido"):
            diseno(MINIMO.replace('animaciones = ["golpe"]', 'animaciones = ["golpe", "golpe"]'))

    def test_falta_juego(self):
        with self.assertRaisesRegex(ErrorDiseno, r"Falta \[juego\]"):
            diseno('[fabrica]\naprobar = []\n')

    def test_duracion_negativa(self):
        with self.assertRaisesRegex(ErrorDiseno, "mayor que 0"):
            diseno(MINIMO.replace("duracion = 0.6", "duracion = -1"))


class TestPlan(unittest.TestCase):
    def test_cadena_del_personaje(self):
        tareas = {t.id: t for t in planificar(diseno())}
        self.assertEqual(tareas["ren/modelo3d"].deps, ("ren/concepto",))
        self.assertEqual(tareas["ren/rig"].deps, ("ren/limpieza",))
        self.assertEqual(tareas["ren/animacion/golpe"].deps, ("ren/rig",))
        self.assertEqual(tareas["ren/voz/grito"].deps, ())
        self.assertTrue(tareas["ren/concepto"].requiere_aprobacion)
        self.assertFalse(tareas["ren/modelo3d"].requiere_aprobacion)

    def test_cada_tarea_va_despues_de_sus_dependencias(self):
        tareas = planificar(diseno())
        posicion = {t.id: i for i, t in enumerate(tareas)}
        for t in tareas:
            for dep in t.deps:
                self.assertLess(posicion[dep], posicion[t.id])

    def test_huella_cambia_solo_si_cambia_lo_que_se_pide(self):
        antes = {t.id: t.huella for t in planificar(diseno())}
        self.assertEqual(antes, {t.id: t.huella for t in planificar(diseno())})
        despues = {t.id: t.huella for t in planificar(diseno(MINIMO.replace("Luchador de fuego", "Luchador de hielo")))}
        self.assertNotEqual(antes["ren/concepto"], despues["ren/concepto"])
        self.assertEqual(antes["ren/voz/grito"], despues["ren/voz/grito"])

    def test_cambiar_de_proveedor_cambia_la_huella(self):
        antes = {t.id: t.huella for t in planificar(diseno())}
        con_voz = MINIMO.replace("intentos_max = 2", 'intentos_max = 2\n\n[fabrica.proveedores]\nvoz = "elevenlabs"')
        despues = {t.id: t.huella for t in planificar(diseno(con_voz))}
        self.assertNotEqual(antes["ren/voz/grito"], despues["ren/voz/grito"])
        self.assertEqual(antes["ren/concepto"], despues["ren/concepto"])
