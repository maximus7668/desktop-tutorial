import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from fabrica.cli import main


def correr(*args: str) -> tuple[int, str, str]:
    salida, errores = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
        codigo = main(list(args))
    return codigo, salida.getvalue(), errores.getvalue()


class TestCli(unittest.TestCase):
    def test_flujo_completo_con_la_plantilla(self):
        with tempfile.TemporaryDirectory() as tmp:
            proyecto = str(Path(tmp) / "juego")
            self.assertEqual(correr("nuevo", proyecto)[0], 0)
            codigo, salida, _ = correr("plan", "-p", proyecto)
            self.assertEqual(codigo, 0)
            self.assertIn("ren/animacion/tecnica_guren", salida)

            for _ in range(4):
                self.assertEqual(correr("ejecutar", "-p", proyecto)[0], 0)
                correr("aprobar", "--todo", "-p", proyecto)
            codigo, salida, _ = correr("estado", "-p", proyecto)
            self.assertIn("Todo aprobado", salida)
            codigo, salida, _ = correr("exportar", "-p", proyecto)
            self.assertEqual(codigo, 0)
            self.assertTrue((Path(proyecto) / "indice_recursos.json").is_file())

    def test_errores_se_explican_y_devuelven_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            codigo, _, errores = correr("plan", "-p", tmp)
            self.assertEqual(codigo, 1)
            self.assertIn("No encuentro", errores)
            correr("nuevo", tmp)
            codigo, _, errores = correr("nuevo", tmp)
            self.assertEqual(codigo, 1)
            self.assertIn("ya existe", errores)
            codigo, _, errores = correr("aprobar", "-p", tmp)
            self.assertEqual(codigo, 1)
            self.assertIn("--todo", errores)
