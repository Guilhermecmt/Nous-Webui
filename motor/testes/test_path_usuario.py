"""O instalador poe <app>\bin no PATH do usuario sem congelar as %VARIAVEIS% que ja' estao la'."""
import os
import subprocess
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(RAIZ, "launchers", "path-nous.ps1")
SUB = r"Software\NousTeste\Environment"

if sys.platform == "win32":
    import winreg


def ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                           ". '%s'; %s" % (LIB, cmd)], capture_output=True, text=True, timeout=60)


@unittest.skipUnless(sys.platform == "win32", "so' no Windows")
class TestPathUsuario(unittest.TestCase):
    def setUp(self):
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, SUB)
        winreg.SetValueEx(k, "Path", 0, winreg.REG_EXPAND_SZ, r"%USERPROFILE%\ferramentas;C:\outra")
        winreg.CloseKey(k)

    def tearDown(self):
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, SUB)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\NousTeste")

    def ler(self):
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, SUB)
        v, t = winreg.QueryValueEx(k, "Path")
        winreg.CloseKey(k)
        return v, t

    def test_adiciona_sem_expandir_e_tira(self):
        r = ps(r"Add-NousPath -Dir 'C:\App Nous\bin' -Sub '%s'" % SUB)
        self.assertEqual(r.returncode, 0, r.stderr)
        v, t = self.ler()
        self.assertEqual(t, winreg.REG_EXPAND_SZ)
        self.assertEqual(v, r"%USERPROFILE%\ferramentas;C:\outra;C:\App Nous\bin")
        ps(r"Add-NousPath -Dir 'C:\App Nous\bin\' -Sub '%s'" % SUB)  # de novo: nao duplica
        self.assertEqual(self.ler()[0].count("App Nous"), 1)
        r = ps(r"Remove-NousPath -Dir 'C:\App Nous\bin' -Sub '%s'" % SUB)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.ler(), (r"%USERPROFILE%\ferramentas;C:\outra", winreg.REG_EXPAND_SZ))


if __name__ == "__main__":
    unittest.main()
