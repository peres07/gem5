# SPDX-License-Identifier: BSD-3-Clause
"""Valida uma simulacao e extrai as metricas da regiao de interesse."""

import argparse
import csv
import re
import sys
from configparser import ConfigParser
from pathlib import Path

from matriz_p12 import d_ponderada, fracao_l1_l1, le_perfil


def extrai(pasta, colunas, mapa=None, previsto=None):
    pasta = Path(pasta)
    flits = le_perfil(pasta)
    msgs = le_perfil(pasta, "msgs")
    if mapa is not None and mapa != flits.roteador:
        raise ValueError(f"{pasta}: mapa aplicado difere do solicitado")

    texto = (pasta / "stats.txt").read_text()
    blocos = re.findall(
        r"Begin Simulation Statistics ----------(.*?)"
        r"---------- End Simulation Statistics", texto, re.S
    )
    if len(blocos) < 2:
        raise ValueError(f"{pasta}: falta o bloco da ROI ou o bloco final")
    stats = dict(
        campos[:2]
        for linha in blocos[0].splitlines()
        if len(campos := linha.split()) >= 2
    )
    prefixo = "system.ruby.network."
    pacotes = int(stats[prefixo + "packets_injected::total"])
    injetados = int(stats[prefixo + "flits_injected::total"])
    recebidos = int(stats[prefixo + "flits_received::total"])
    if sum(map(sum, msgs.matriz)) != pacotes:
        raise ValueError(f"{pasta}: matriz de pacotes inconsistente")
    if sum(map(sum, flits.matriz)) != injetados:
        raise ValueError(f"{pasta}: matriz de flits inconsistente")

    saida = (pasta / "simout.txt").read_text()
    checksum = re.findall(r"^checksum=(\d+) esperado=(\d+)$", saida, re.M)
    if len(checksum) != 1 or checksum[0][0] != checksum[0][1]:
        raise ValueError(f"{pasta}: checksum ausente ou incorreto")
    pares = re.findall(r"^thread=(\d+) cpu=(\d+) soma=\d+$", saida, re.M)
    nucleos = sum(nome.startswith("l1_cntrl") for nome in flits.nomes)
    if sorted((int(t), int(cpu)) for t, cpu in pares) != [
        (i, i) for i in range(nucleos)
    ]:
        raise ValueError(f"{pasta}: correspondencia thread-CPU incorreta")

    medida = d_ponderada(flits, flits.roteador, colunas)
    saltos = float(stats[prefixo + "average_hops"])
    # Injetados e recebidos podem diferir no limite da ROI.
    diametro = colunas + nucleos // colunas - 2
    tolerancia = 0.01 + diametro * abs(injetados - recebidos) / injetados
    if not recebidos or abs(medida - saltos) > tolerancia:
        raise ValueError(f"{pasta}: Dmed={medida} difere de average_hops={saltos}")

    config = ConfigParser(interpolation=None)
    config.read(pasta / "config.ini")
    dominio = config["system.ruby.network"]["clk_domain"]
    periodo = int(config[dominio]["clock"])
    ticks = int(stats["simTicks"])
    return {
        "d_prev": previsto if previsto is not None else medida,
        "d_med": medida,
        "average_hops": saltos,
        "latencia_rede_ciclos": (
            float(stats[prefixo + "average_packet_network_latency"]) / periodo
        ),
        "latencia_fila_ciclos": (
            float(stats[prefixo + "average_packet_queueing_latency"]) / periodo
        ),
        "fracao_l1_l1": fracao_l1_l1(flits),
        "roi_ticks": ticks,
        "roi_segundos": ticks / int(stats["simFreq"]),
        "pacotes_injetados": pacotes,
        "flits_injetados": injetados,
        "flits_recebidos": recebidos,
        "checksum": int(checksum[0][0]),
    }


def grava_csv(saida, linhas):
    tabela = csv.DictWriter(saida, fieldnames=list(linhas[0]))
    tabela.writeheader()
    tabela.writerows(linhas)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("diretorio", type=Path)
    ap.add_argument("--colunas", type=int, default=4)
    args = ap.parse_args()
    grava_csv(sys.stdout, [extrai(args.diretorio, args.colunas)])
