"""Ninguem fora do motor fala direto com o Ollama (11434): todos passam pelo nous-motor (8989)."""
import os
import re
import subprocess
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FORA = ("motor/", "installer/", "bkp/", "docs/", "mockups/", "tests-tela/")
# nous-env.ps1: o unico lugar que diz onde o Ollama de verdade mora (NOUS_OLLAMA_REAL);
# register_motor.py: reconhece a URL antiga do Ollama no banco para troca-la.
PERMITIDOS = {"launchers/nous-env.ps1", "ajustes/register_motor.py"}


def rastreados():
    out = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True).stdout
    for f in out.splitlines():
        if not f.endswith((".py", ".ts", ".js", ".ps1")):
            continue
        if f in PERMITIDOS or f.startswith(FORA) or "/testes/" in f or "/tests/" in f or f.startswith("code/testes"):
            continue
        yield f


class TestSem11434(unittest.TestCase):
    def test_nenhum_11434_fora_do_motor(self):
        achados = []
        for f in rastreados():
            with open(os.path.join(RAIZ, f), encoding="utf-8", errors="replace") as h:
                for i, linha in enumerate(h, 1):
                    if "11434" in linha:
                        achados.append("%s:%d: %s" % (f, i, linha.strip()[:120]))
        self.assertEqual(achados, [], "\n".join(achados))

    def test_valves_de_url_leem_o_ambiente(self):
        # um Field(default="http://...") fixo ignora o OLLAMA_BASE_URL do launcher
        fixo = re.compile(r'(OLLAMA[A-Z_]*)\s*:\s*str\s*=\s*Field\(\s*default\s*=\s*"http')
        achados = []
        for f in rastreados():
            if not f.endswith(".py"):
                continue
            with open(os.path.join(RAIZ, f), encoding="utf-8", errors="replace") as h:
                for i, linha in enumerate(h, 1):
                    if fixo.search(linha):
                        achados.append("%s:%d" % (f, i))
        self.assertEqual(achados, [], "\n".join(achados))


if __name__ == "__main__":
    unittest.main()
