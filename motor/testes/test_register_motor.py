import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(RAIZ, "ajustes", "register_motor.py")
VELHO = "http://127.0.0.1:11434"
MOTOR = "http://127.0.0.1:8989"


def rodar(d, *extra):
    amb = {k: v for k, v in os.environ.items() if k not in ("DATA_DIR", "NOUS_DATA_DIR")}
    return subprocess.run([sys.executable, SCRIPT, "--data-dir", d, *extra], capture_output=True, text=True, env=amb, timeout=60)


class TestRegisterMotor(unittest.TestCase):
    def test_config_por_chave(self):
        with tempfile.TemporaryDirectory() as d:
            cx = sqlite3.connect(os.path.join(d, "webui.db"))
            cx.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
            cx.execute("INSERT INTO config VALUES ('ollama.base_urls', ?, 1)", (json.dumps([VELHO]),))
            cx.execute("INSERT INTO config VALUES ('rag.ollama.base_url', ?, 1)", (json.dumps(VELHO),))
            cx.commit()
            cx.close()
            r = rodar(d)
            self.assertEqual(r.returncode, 0, r.stderr)
            cx = sqlite3.connect(os.path.join(d, "webui.db"))
            v = dict(cx.execute("SELECT key, value FROM config").fetchall())
            self.assertEqual(json.loads(v["ollama.base_urls"]), [MOTOR])
            self.assertEqual(json.loads(v["rag.ollama.base_url"]), MOTOR)
            antes = cx.execute("SELECT key, updated_at FROM config ORDER BY key").fetchall()
            cx.close()
            rodar(d)
            cx = sqlite3.connect(os.path.join(d, "webui.db"))
            self.assertEqual(cx.execute("SELECT key, updated_at FROM config ORDER BY key").fetchall(), antes)
            cx.close()
            r = rodar(d, "--url", VELHO)
            cx = sqlite3.connect(os.path.join(d, "webui.db"))
            v = dict(cx.execute("SELECT key, value FROM config").fetchall())
            self.assertEqual(json.loads(v["ollama.base_urls"]), [VELHO])
            cx.close()

    def test_config_em_blob(self):
        with tempfile.TemporaryDirectory() as d:
            cx = sqlite3.connect(os.path.join(d, "webui.db"))
            cx.execute("CREATE TABLE config (id INTEGER PRIMARY KEY, data TEXT, version INTEGER, created_at TEXT, updated_at TEXT)")
            dados = {"ollama": {"enable": True, "base_urls": [VELHO]}, "rag": {"ollama": {"base_url": VELHO}}}
            cx.execute("INSERT INTO config (data, version, created_at, updated_at) VALUES (?, 0, 'x', 'antes')", (json.dumps(dados),))
            cx.commit()
            cx.close()
            self.assertEqual(rodar(d).returncode, 0)
            cx = sqlite3.connect(os.path.join(d, "webui.db"))
            data, upd = cx.execute("SELECT data, updated_at FROM config").fetchone()
            data = json.loads(data)
            self.assertEqual(data["ollama"]["base_urls"], [MOTOR])
            self.assertTrue(data["ollama"]["enable"])
            self.assertEqual(data["rag"]["ollama"]["base_url"], MOTOR)
            cx.close()
            rodar(d)
            cx = sqlite3.connect(os.path.join(d, "webui.db"))
            self.assertEqual(cx.execute("SELECT updated_at FROM config").fetchone()[0], upd)
            cx.close()

    def test_sem_banco_nao_faz_nada(self):
        with tempfile.TemporaryDirectory() as d:
            r = rodar(d)
            self.assertEqual(r.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(d, "webui.db")))

    def test_varias_urls_vira_uma(self):
        with tempfile.TemporaryDirectory() as d:
            cx = sqlite3.connect(os.path.join(d, "webui.db"))
            cx.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
            cx.execute("INSERT INTO config VALUES ('ollama.base_urls', ?, 1)", (json.dumps([VELHO, "http://outra:11434"]),))
            cx.commit()
            cx.close()
            rodar(d)
            cx = sqlite3.connect(os.path.join(d, "webui.db"))
            v = dict(cx.execute("SELECT key, value FROM config").fetchall())
            # so' troca a URL local do Ollama; um servidor de outra maquina que o usuario pos fica
            self.assertEqual(json.loads(v["ollama.base_urls"]), [MOTOR, "http://outra:11434"])
            cx.close()


if __name__ == "__main__":
    unittest.main()
