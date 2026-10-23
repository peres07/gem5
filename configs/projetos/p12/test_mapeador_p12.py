import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from matriz_p12 import Perfil, d_ponderada, le_perfil
from mapeador_p12 import aleatorio, confere, guloso, linear, otimo


def perfil_teste(padrao):
    nomes = [f"l1_cntrl{i}" for i in range(8)]
    matriz = [[0] * 8 for _ in range(8)]
    for i in range(8):
        for j in range(8):
            if i != j and (
                (padrao == "anel" and (j - i) % 8 in (1, 7))
                or (padrao == "grupos" and i % 2 == j % 2)
            ):
                matriz[i][j] = 1
    return Perfil(nomes, matriz, dict(zip(nomes, range(8))))


class TesteMapeador(unittest.TestCase):
    def test_grupos(self):
        p = perfil_teste("grupos")
        a = linear(p, 2, 4)
        g = guloso(p, 2, 4)
        o = otimo(p, 2, 4)
        self.assertAlmostEqual(d_ponderada(p, a, 4), 2)
        self.assertAlmostEqual(d_ponderada(p, o, 4), 16 / 12)
        self.assertAlmostEqual(d_ponderada(p, g, 4), 16 / 12)
        self.assertEqual(g, guloso(p, 2, 4))

    def test_anel(self):
        p = perfil_teste("anel")
        self.assertAlmostEqual(d_ponderada(p, otimo(p, 2, 4), 4), 1)
        self.assertLessEqual(d_ponderada(p, guloso(p, 2, 4), 4),
                             d_ponderada(p, linear(p, 2, 4), 4))

    def test_vazia(self):
        p = perfil_teste("vazia")
        confere(guloso(p, 2, 4), p.nomes, 8)
        with self.assertRaises(ValueError):
            d_ponderada(p, linear(p, 2, 4), 4)

    def test_aleatorio(self):
        p = perfil_teste("grupos")
        self.assertEqual(aleatorio(p, 2, 4, 11), aleatorio(p, 2, 4, 11))
        self.assertNotEqual(aleatorio(p, 2, 4, 11), aleatorio(p, 2, 4, 12))

    def test_leitor(self):
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "p12_nos.csv").write_text(
                "ni,controlador,roteador\n"
                "0,system.ruby.l1_cntrl0,0\n"
                "1,system.ruby.l1_cntrl1,1\n"
            )
            (pasta / "stats.txt").write_text(
                "---------- Begin Simulation Statistics ----------\n"
                "system.ruby.network.p12_flits_l1_cntrl0::l1_cntrl1 3\n"
                "---------- End Simulation Statistics   ----------\n"
            )
            p = le_perfil(pasta)
            self.assertEqual(p.matriz, [[0, 3], [0, 0]])
            self.assertEqual(d_ponderada(p, p.roteador, 2), 1)


if __name__ == "__main__":
    unittest.main()
