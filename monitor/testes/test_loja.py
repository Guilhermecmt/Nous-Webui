import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import nous_monitor  # noqa: E402


class TestVelocidade(unittest.TestCase):
    HW = {"tier": "gpu-16", "vram_gb": 16, "gpu_bw": 640, "ram_bw": 80}

    def test_modelo_minusculo_nao_divide_por_zero(self):
        # all-minilm:22m tem 46 MB: round(0.046, 1) == 0.0 e o /model/check dava erro 500
        for hw in (self.HW, {**self.HW, "tier": "cpu", "gpu_bw": 0}):
            r = nous_monitor._speed({"download_gb": 0.0}, hw)
            self.assertGreater(r["tps"], 0)

    def test_modelo_normal(self):
        self.assertEqual(nous_monitor._speed({"download_gb": 2.5}, self.HW)["onde"], "gpu")


if __name__ == "__main__":
    unittest.main()
