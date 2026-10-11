import io
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from fabrica import cli
from fabrica.agentes import ErrorAgente
from fabrica.agentes.claude import ClienteClaude
from fabrica.diseno import cargar, validar
from fabrica.director import Director
from fabrica.idear import ESQUEMA, SISTEMA, escribir, idear

MUESTRA = {
    "nombre": "Tormenta de \"Acero\"",
    "estilo": "Anime 3D con cel-shading, contorno negro grueso y colores saturados. " * 3,
    "personajes": [
        {
            "id": "Kaito Ráiden",
            "nombre": "Kaito Raiden",
            "descripcion": "Samurái de 25 años, pelo negro con mechas amarillas, armadura ligera azul. " * 3,
            "voz": "Hombre joven, voz grave y tranquila.",
            "altura": 1.82,
            "animaciones": ["guardia", "correr", "Técnica Raikō", "guardia"],
            "frases": [
                {"id": "entrada", "texto": "Acabemos con esto."},
                {"id": "tecnica", "texto": "¡Raikō... Zan! \\ \"rayo\""},
                {"id": "", "texto": "sin id"},
            ],
        },
        {
            "id": "sonido",
            "nombre": "Mika",
            "descripcion": "Ninja de 18 años con bufanda roja corta.",
            "voz": "",
            "altura": 99,
            "animaciones": [],
            "frases": [],
        },
        {"id": "vacio", "nombre": "", "descripcion": "", "voz": "", "altura": 1.7, "animaciones": [], "frases": []},
    ],
    "sonidos": [
        {"id": "golpe", "descripcion": "Quick punch impact", "duracion": 0.2, "bucle": False},
        {"id": "rayo", "descripcion": "Continuous lightning beam", "duracion": 4, "bucle": True},
        {"id": "golpe", "descripcion": "Another punch", "duracion": 99, "bucle": False},
    ],
    "musica": [
        {"id": "tema_combate", "descripcion": "Fast taiko and electric guitar battle theme, 170 bpm", "duracion": 120,
         "instrumental": True},
        {"id": "menu", "descripcion": "Calm koto menu theme", "duracion": 2, "instrumental": False},
    ],
}


class ClaudeQueResponde:
    def __init__(self, datos):
        self.datos = datos
        self.llamadas = []

    def json(self, sistema, contenido, esquema, max_tokens=16000):
        self.llamadas.append((sistema, contenido, esquema, max_tokens))
        return self.datos


class TestIdear(unittest.TestCase):
    def setUp(self):
        self.texto = escribir(MUESTRA, "Un juego de samuráis\ncon poderes de rayo.")
        self.diseno = validar(tomllib.loads(self.texto))

    def test_el_diseno_es_valido_y_respeta_lo_pedido(self):
        d = self.diseno
        self.assertEqual(d.nombre, 'Tormenta de "Acero"')
        self.assertEqual([p.id for p in d.personajes], ["kaito_raiden", "sonido_2"])  # «sonido» está reservado
        kaito = d.personajes[0]
        self.assertEqual(kaito.altura, 1.82)
        self.assertEqual(kaito.animaciones, ("guardia", "correr", "tecnica_raiko"))  # sin la repetida
        self.assertEqual(dict(kaito.frases)["tecnica"], '¡Raikō... Zan! \\ "rayo"')
        self.assertEqual(len(kaito.frases), 2)
        self.assertTrue(kaito.descripcion.startswith("Samurái de 25 años"))
        self.assertIsNone(d.personajes[1].altura)  # 99 m no es una altura
        self.assertEqual([(s.id, s.duracion, s.bucle) for s in d.sonidos],
                         [("golpe", 0.5, False), ("rayo", 4.0, True), ("golpe_2", 30.0, False)])
        self.assertEqual([(m.id, m.duracion, m.instrumental) for m in d.musica],
                         [("tema_combate", 120.0, True), ("menu", 10.0, False)])

    def test_lleva_la_idea_y_las_explicaciones_de_la_plantilla(self):
        self.assertTrue(self.texto.startswith("# juego.toml escrito por Claude"))
        self.assertIn("#   Un juego de samuráis\n#   con poderes de rayo.", self.texto)
        self.assertIn("# Quién hace cada tipo de recurso.", self.texto)
        self.assertIn('voz_id = ""', self.texto)
        self.assertIn('descripcion = """\n', self.texto)  # lo largo, en varias líneas
        self.assertEqual(set(self.diseno.proveedores.values()), {"simulado"})

    def test_la_fabrica_lo_usa_tal_cual(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "juego.toml").write_text(self.texto, encoding="utf-8")
            d = Director(Path(tmp))
            self.assertIn("kaito_raiden/animacion/tecnica_raiko", d.por_id)

    def test_idear_pide_a_claude_con_el_esquema(self):
        claude = ClaudeQueResponde(MUESTRA)
        self.assertEqual(idear("  samuráis  ", claude), escribir(MUESTRA, "samuráis"))
        sistema, contenido, esquema, max_tokens = claude.llamadas[0]
        self.assertIs(sistema, SISTEMA)
        self.assertEqual(contenido, [{"type": "text", "text": "samuráis"}])
        self.assertIs(esquema, ESQUEMA)
        self.assertEqual(max_tokens, 32000)

    def test_sin_idea_o_sin_personajes(self):
        with self.assertRaisesRegex(ErrorAgente, "Cuenta tu idea"):
            idear("   ", ClaudeQueResponde(MUESTRA))
        with self.assertRaisesRegex(ErrorAgente, "ningún personaje"):
            escribir({**MUESTRA, "personajes": []}, "idea")

    def test_el_esquema_cumple_las_reglas_de_la_salida_estructurada(self):
        def revisar(nodo, donde="raiz"):
            if nodo.get("type") == "object":
                self.assertIs(nodo.get("additionalProperties"), False, donde)
                self.assertEqual(sorted(nodo["required"]), sorted(nodo["properties"]), donde)
                for clave, hijo in nodo["properties"].items():
                    revisar(hijo, f"{donde}.{clave}")
            if nodo.get("type") == "array":
                revisar(nodo["items"], f"{donde}[]")
            for prohibida in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"):
                self.assertNotIn(prohibida, nodo, donde)

        revisar(ESQUEMA)


class TestOrdenIdear(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.carpeta = Path(self._tmp.name) / "mi_juego"
        listo = mock.patch.object(ClienteClaude, "disponible", return_value=None)  # como si hubiera clave
        listo.start()
        self.addCleanup(listo.stop)

    def orden(self, *args):
        salida, errores = io.StringIO(), io.StringIO()
        with redirect_stdout(salida), redirect_stderr(errores):
            codigo = cli.main(list(args))
        return codigo, salida.getvalue(), errores.getvalue()

    def test_escribe_el_proyecto(self):
        with mock.patch.object(ClienteClaude, "json", return_value=MUESTRA) as pedido:
            codigo, salida, _ = self.orden("idear", str(self.carpeta), "samuráis", "con", "rayos", "--esfuerzo", "medium")
        self.assertEqual(codigo, 0)
        self.assertEqual(pedido.call_args.args[1], [{"type": "text", "text": "samuráis con rayos"}])
        self.assertIn("Personajes: Kaito Raiden, Mika", salida)
        self.assertEqual(cargar(self.carpeta / "juego.toml").nombre, 'Tormenta de "Acero"')

    def test_idea_desde_archivo(self):
        archivo = Path(self._tmp.name) / "idea.txt"
        archivo.write_text("Lucha de robots gigantes.", encoding="utf-8")
        with mock.patch.object(ClienteClaude, "json", return_value=MUESTRA) as pedido:
            codigo, _, _ = self.orden("idear", str(self.carpeta), "--archivo", str(archivo))
        self.assertEqual(codigo, 0)
        self.assertEqual(pedido.call_args.args[1][0]["text"], "Lucha de robots gigantes.")

    def test_no_sobrescribe_ni_trabaja_sin_idea(self):
        codigo, _, errores = self.orden("idear", str(self.carpeta))
        self.assertEqual(codigo, 1)
        self.assertIn("Cuenta tu idea", errores)
        self.carpeta.mkdir()
        (self.carpeta / "juego.toml").write_text("", encoding="utf-8")
        codigo, _, errores = self.orden("idear", str(self.carpeta), "otra idea")
        self.assertEqual(codigo, 1)
        self.assertIn("ya existe", errores)

    def test_sin_clave_no_empieza(self):
        with mock.patch.object(ClienteClaude, "disponible", return_value="Falta la clave de Claude"):
            codigo, salida, errores = self.orden("idear", str(self.carpeta), "idea")
        self.assertEqual(codigo, 1)
        self.assertIn("Falta la clave de Claude", errores)
        self.assertEqual(salida, "")

    def test_errores_de_claude_se_explican(self):
        with mock.patch.object(ClienteClaude, "json", side_effect=ErrorAgente("Claude pide esperar")):
            codigo, _, errores = self.orden("idear", str(self.carpeta), "idea")
        self.assertEqual(codigo, 1)
        self.assertIn("Error: Claude pide esperar", errores)
        self.assertFalse((self.carpeta / "juego.toml").exists())


if __name__ == "__main__":
    unittest.main()
