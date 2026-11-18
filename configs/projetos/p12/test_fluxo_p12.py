# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

import csv
import io
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from analisa_p12 import agrega
from campanha_p12 import (
    PERTURBACOES,
    estabilidade,
    mapas_prontos,
    passada_avaliacoes,
    passada_perfis,
    politicas,
)
from extrai_p12 import (
    REDE,
    confere_saltos,
    extrai,
)
from fluxo_p12 import (
    MALHAS,
    PROGRAMAS,
    Fluxo,
)
from matriz_p12 import distancia
from valida_sintetico_p12 import (
    LADO,
    NOS,
    PACOTES,
    valida,
)


def grava_execucao(pasta, mapa=None):
    if mapa is None:
        mapa = {f"l1_cntrl{i}": i for i in range(8)}
    (pasta / "p12_nos.csv").write_text(
        "ni,controlador,roteador\n"
        + "".join(
            f"{i},system.ruby.{n},{r}\n"
            for i, (n, r) in enumerate(sorted(mapa.items()))
        )
    )
    hops = distancia(mapa["l1_cntrl0"], mapa["l1_cntrl1"], 4)
    (pasta / "stats.txt").write_text(
        "---------- Begin Simulation Statistics ----------\n"
        "simTicks 100000\n"
        f"{REDE}.p12_msgs_l1_cntrl0::l1_cntrl1 100\n"
        f"{REDE}.p12_flits_l1_cntrl0::l1_cntrl1 500\n"
        f"{REDE}.packets_injected::total 100\n"
        f"{REDE}.flits_injected::total 500\n"
        f"{REDE}.flits_received::total 500\n"
        f"{REDE}.average_hops {hops}\n"
        f"{REDE}.average_packet_network_latency 10000\n"
        f"{REDE}.average_packet_queueing_latency 500\n"
        "---------- End Simulation Statistics ----------\n"
        "---------- Begin Simulation Statistics ----------\n"
        "simTicks 999000\n"
        "---------- End Simulation Statistics ----------\n"
    )
    (pasta / "config.ini").write_text(
        f"[{REDE}]\nclk_domain=system.ruby.clk_domain\n"
        "[system.ruby.clk_domain]\nclock=500\n"
    )


def log_valido():
    return "".join(f"thread={t} cpu={t} soma={t}\n" for t in range(8)) + (
        "checksum=28 esperado=28\n"
    )


class TesteFluxo(unittest.TestCase):
    def setUp(self):
        temporario = TemporaryDirectory()
        self.addCleanup(temporario.cleanup)
        self.pasta = Path(temporario.name)

    def test_extracao_e_rejeicao(self):
        grava_execucao(self.pasta)
        log = self.pasta / "simulador.log"
        log.write_text(log_valido())
        metricas = extrai(self.pasta, 2, 4, limite=0)
        self.assertEqual(metricas["simTicks"], 100000)
        self.assertEqual(metricas["latencia_rede_ciclos"], 20)
        self.assertEqual(metricas["latencia_fila_ciclos"], 1)
        self.assertEqual(metricas["distancia_medida"], 1)
        self.assertEqual(metricas["phi"], 1)

        stats = self.pasta / "stats.txt"
        original = stats.read_text()
        stats.write_text(
            original.replace(
                "flits_injected::total 500", "flits_injected::total 501"
            )
        )
        with self.assertRaisesRegex(ValueError, "conservacao"):
            extrai(self.pasta, 2, 4)
        stats.write_text(original)
        log.write_text(log_valido().replace("cpu=7", "cpu=6"))
        with self.assertRaisesRegex(ValueError, "thread-CPU"):
            extrai(self.pasta, 2, 4)
        log.write_text(log_valido().replace("esperado=28", "esperado=29"))
        with self.assertRaisesRegex(ValueError, "checksum"):
            extrai(self.pasta, 2, 4)
        log.write_text(log_valido())
        mapa = self.pasta / "mapa.json"
        mapa.write_text(json.dumps({"linhas": 2, "colunas": 4, "mapa": {}}))
        with self.assertRaisesRegex(ValueError, "difere do JSON"):
            extrai(self.pasta, 2, 4, mapa)

    def test_limite_de_transito(self):
        # Um flit de 4 saltos fica na rede ao final da ROI.
        confere_saltos(500, 499, 503, Decimal(1), 4, 1)
        # Injetados e recebidos podem empatar com um flit em cada fronteira.
        confere_saltos(500, 500, 501, Decimal(1), 4, 1)
        with self.assertRaisesRegex(ValueError, "average_hops"):
            confere_saltos(500, 500, 510, Decimal(1), 4, 1)

    def test_duas_passadas_retomada_e_estabilidade(self):
        gem5 = self.pasta / "gem5.opt"
        gem5.touch()
        (self.pasta / "grupos").touch()
        fluxo = Fluxo(self.pasta / "saida", gem5, self.pasta, 10, 4, 0)
        casos = [("grupos", 8)]

        def simula(cmd, *, cwd, stdout, **kwargs):
            pasta = Path(cmd[2])
            mapa = next(
                (
                    s.split("=", 1)[1]
                    for s in cmd
                    if s.startswith("--p12-mapa=")
                ),
                None,
            )
            grava_execucao(
                pasta,
                json.loads(Path(mapa).read_text())["mapa"] if mapa else None,
            )
            stdout.write(log_valido())
            return type("Resultado", (), {"returncode": 0})()

        with (
            patch("fluxo_p12.subprocess.run", side_effect=simula) as run,
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            passada_perfis(pool, fluxo, casos, 1)
            mapas = list(mapas_prontos(fluxo, casos, 1))
            linhas = passada_avaliacoes(pool, fluxo, mapas)
            self.assertEqual(len(linhas), 18)
            self.assertEqual(run.call_count, 19)
            self.assertTrue(
                all(
                    l["distancia_prevista"] == l["average_hops"]
                    for l in linhas
                )
            )
            self.assertEqual(linhas, passada_avaliacoes(pool, fluxo, mapas))
            self.assertEqual(run.call_count, 19)
            (Path(linhas[0]["execucao"]) / "stats.txt").unlink()
            self.assertEqual(linhas, passada_avaliacoes(pool, fluxo, mapas))
            self.assertEqual(run.call_count, 20)
            (comparacao,) = estabilidade(pool, fluxo, mapas, 1)
            self.assertEqual(comparacao["diferenca_relativa"], 0)
            self.assertTrue(comparacao["mesmo_mapa"])

    def test_tamanho_campanha(self):
        self.assertEqual(len(PROGRAMAS) * len(MALHAS), 6)
        total = sum(len(politicas(n)) for n in MALHAS)
        self.assertEqual(total * len(PROGRAMAS) * len(PERTURBACOES), 99)

    def test_analise_pareada(self):
        arq = io.StringIO()
        writer = csv.writer(arq)
        writer.writerow(
            [
                "programa",
                "nucleos",
                "unidade_mapa",
                "politica",
                "semente_mapa",
                "semente_perturbacao",
                "simTicks",
                "average_hops",
                "distancia_prevista",
                "distancia_medida",
                "latencia_rede_ciclos",
            ]
        )
        for p, m in politicas(8):
            for s in PERTURBACOES:
                base = s * 100
                ticks = base // 2 if p == "guloso" else base
                writer.writerow(
                    ["grupos", 8, "flits", p, m, s, ticks, 2, 2, 2, 5]
                )
        arq.seek(0)
        dados = {r["politica"]: r for r in agrega(arq)}
        self.assertEqual(dados["guloso"]["tempo"], 0.5)
        self.assertEqual(dados["guloso"]["erro_padrao"], 0)
        self.assertEqual(dados["guloso"]["reducao_tempo"], 50)

    def test_transposicao_sintetica(self):
        nos = self.pasta / "p12_nos.csv"
        nomes = [
            f"{tipo}_cntrl{i}" for tipo in ("l1", "dir") for i in range(NOS)
        ]
        nos.write_text(
            "ni,controlador,roteador\n"
            + "".join(
                f"{i},system.ruby.{nome},{i % NOS}\n"
                for i, nome in enumerate(nomes)
            )
        )
        regs = []
        for x in range(LADO):
            for y in range(LADO):
                par = f"l1_cntrl{y * LADO + x}::dir_cntrl{x * LADO + y}"
                regs.append(f"{REDE}.p12_msgs_{par} {PACOTES}\n")
                regs.append(f"{REDE}.p12_flits_{par} {5 * PACOTES}\n")
        total = PACOTES * NOS
        stats = self.pasta / "stats.txt"
        texto = (
            "---------- Begin Simulation Statistics ----------\n"
            + "".join(regs)
            + f"{REDE}.packets_injected::total {total}\n"
            + f"{REDE}.flits_injected::total {5 * total}\n"
            + f"{REDE}.flits_received::total {5 * total}\n"
            + f"{REDE}.average_hops 2.5\n"
            + "---------- End Simulation Statistics ----------\n"
        )
        stats.write_text(texto)
        valida(self.pasta, "transpose", 2)
        # Conservacao ainda vale ao deslocar uma celula para destino errado.
        stats.write_text(
            texto.replace("l1_cntrl0::dir_cntrl0", "l1_cntrl0::dir_cntrl1")
        )
        with self.assertRaisesRegex(ValueError, "matriz msgs inesperada"):
            valida(self.pasta, "transpose", 2)


if __name__ == "__main__":
    unittest.main()
