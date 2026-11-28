import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mapeador_p12 import (
    POLITICAS,
    aleatorio,
    confere,
    guloso,
    linear,
    otimo,
)
from matriz_p12 import (
    Perfil,
    d_ponderada,
    le_perfil,
)


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
    def test_politicas(self):
        self.assertEqual(
            set(POLITICAS), {"linear", "aleatorio", "guloso", "otimo"}
        )

    def test_grupos(self):
        p = perfil_teste("grupos")
        a = linear(p, 2, 4)
        g = guloso(p, 2, 4)
        o = otimo(p, 2, 4)
        self.assertAlmostEqual(d_ponderada(p, a, 4), 2)
        # Dois blocos 2x2 no otimo recuperam a distancia da figura 21.2.
        self.assertAlmostEqual(d_ponderada(p, o, 4), 16 / 12)
        figura = dict(zip(p.nomes, (0, 2, 1, 3, 4, 6, 5, 7)))
        self.assertAlmostEqual(d_ponderada(p, figura, 4), 16 / 12)
        # O desempate central da secao 21.2.4 deixa o 2o grupo nas bordas.
        self.assertEqual([g[n] for n in p.nomes], [1, 0, 2, 4, 5, 3, 6, 7])
        self.assertEqual(d_ponderada(p, g, 4), 2)
        self.assertEqual(g, guloso(p, 2, 4))

    def test_anel(self):
        p = perfil_teste("anel")
        self.assertAlmostEqual(d_ponderada(p, otimo(p, 2, 4), 4), 1)
        self.assertLessEqual(
            d_ponderada(p, guloso(p, 2, 4), 4),
            d_ponderada(p, linear(p, 2, 4), 4),
        )

    def test_anel_4x4_do_capitulo(self):
        nomes = [f"l1_cntrl{i}" for i in range(16)]
        base = dict(zip(nomes, range(16)))
        matriz = [
            [int((j - i) % 16 in (1, 15)) for j in range(16)]
            for i in range(16)
        ]
        p = Perfil(nomes, matriz, base)
        ordem = (0, 1, 2, 3, 7, 6, 5, 4, 8, 9, 10, 11, 15, 14, 13, 12)
        self.assertEqual(d_ponderada(p, base, 4), 30 / 16)
        self.assertEqual(d_ponderada(p, dict(zip(nomes, ordem)), 4), 18 / 16)
        with self.assertRaisesRegex(ValueError, "limitada a 8 L1"):
            otimo(p, 4, 4)

    def test_trafego_de_fixo_para_l1_entra_no_custo_linear(self):
        p = perfil_teste("vazia")
        p.nomes.append("l2_cntrl0")
        p.roteador["l2_cntrl0"] = 7
        for linha in p.matriz:
            linha.append(0)
        p.matriz.append([100] + [0] * 8)
        mapa = guloso(p, 2, 4)
        self.assertEqual(mapa["l2_cntrl0"], 7)
        self.assertEqual(mapa["l1_cntrl0"], 7)
        self.assertEqual(d_ponderada(p, mapa, 4), 0)

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
