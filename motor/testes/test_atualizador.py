"""O atualizador copia com robocopy /MIR: o que nao vem no pacote e nao esta' em EXCLUI_DIRS e' apagado."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(RAIZ, "atualizacao", "nous-atualizar.ps1")


def excluidos(texto=None):
    texto = texto if texto is not None else open(SCRIPT, encoding="utf-8-sig").read()
    m = re.search(r"^\$EXCLUI_DIRS\s*=\s*@\(([^)]*)\)", texto, re.M)
    return re.findall(r'"([^"]+)"', m.group(1))


class TestAtualizadorPreserva(unittest.TestCase):
    def test_pastas_instaladas_fora_do_pacote_ficam(self):
        ex = excluidos()
        for pasta in ("runtime", "bin", "node_modules", "bkp"):
            self.assertIn(pasta, ex)

    @unittest.skipUnless(shutil.which("robocopy"), "so' no Windows")
    def test_robocopy_de_verdade(self):
        with tempfile.TemporaryDirectory() as d:
            pacote, app = os.path.join(d, "pacote"), os.path.join(d, "app")
            os.makedirs(os.path.join(pacote, "motor"))
            open(os.path.join(pacote, "motor", "nous_motor.py"), "w").close()
            for p in ("runtime/node/node.exe", "motor/bin/llama-server.exe", "bin/nous.cmd", "velho.txt"):
                os.makedirs(os.path.dirname(os.path.join(app, p)) or app, exist_ok=True)
                open(os.path.join(app, p), "w").close()
            subprocess.run(["robocopy", pacote, app, "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XD", *excluidos()],
                           capture_output=True)
            self.assertTrue(os.path.exists(os.path.join(app, "runtime/node/node.exe")))
            self.assertTrue(os.path.exists(os.path.join(app, "motor/bin/llama-server.exe")))
            self.assertTrue(os.path.exists(os.path.join(app, "bin/nous.cmd")))
            self.assertTrue(os.path.exists(os.path.join(app, "motor/nous_motor.py")))
            self.assertFalse(os.path.exists(os.path.join(app, "velho.txt")))


if __name__ == "__main__":
    unittest.main()
