# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Valida a ROI e extrai uma linha de metricas por avaliacao."""

import argparse
import csv
import json
import re
import sys
from configparser import ConfigParser
from configparser import Error as IniError
from decimal import (
    Decimal,
    InvalidOperation,
)
from pathlib import Path

from matriz_p12 import (
    d_ponderada,
    distancia,
    fracao_l1_l1,
    le_bloco,
    le_perfil,
)

REDE = "system.ruby.network"
THREAD = re.compile(r"thread=(\d+) cpu=(-?\d+) soma=(\d+)")
CHECKSUM = re.compile(r"checksum=(\d+) esperado=(\d+)")
TRANSITO_PADRAO = 32  # Limite assumido por fronteira da ROI, nao uma medida.


def confere_log(pasta, nucleos):
    somas = {}
    checksums = []
    for linha in (pasta / "simulador.log").read_text().splitlines():
        if achou := THREAD.fullmatch(linha.strip()):
            t, cpu, soma = map(int, achou.groups())
            if t in somas or t != cpu:
                raise ValueError(f"associacao thread-CPU invalida: {linha}")
            somas[t] = soma
        if achou := CHECKSUM.fullmatch(linha.strip()):
            checksums.append(tuple(map(int, achou.groups())))
    if set(somas) != set(range(nucleos)):
        raise ValueError("faltam registros de threads no log")
    total = sum(somas.values()) % (1 << 64)
    if checksums != [(total, total)]:
        raise ValueError("checksum ausente ou incorreto")
    return total


def estatistica(stats, chave):
    try:
        valor = Decimal(stats[chave])
    except (KeyError, InvalidOperation) as erro:
        raise ValueError(f"estatistica ausente ou invalida: {chave}") from erro
    if not valor.is_finite() or valor < 0:
        raise ValueError(f"estatistica invalida: {chave}={valor}")
    return valor


def confere_saltos(injetados, recebidos, custo, hops, diametro, limite):
    """Limita o efeito dos flits ja presentes no inicio ou restantes no fim."""
    saldo = injetados - recebidos
    if abs(saldo) > limite:
        raise ValueError(f"saldo de {saldo} flits excede limite {limite}")
    entram = min(limite, recebidos, limite - saldo)
    saem = min(limite, injetados, limite + saldo)
    diferenca = hops * recebidos - custo
    # O gem5 imprime medias nao inteiras com seis casas por padrao.
    erro_texto = Decimal("0.0000005") * recebidos
    if (
        not -saem * diametro - erro_texto
        <= diferenca
        <= (entram * diametro + erro_texto)
    ):
        raise ValueError("distancia medida incompativel com average_hops")


def extrai(pasta, linhas, colunas, mapa_json=None, limite=TRANSITO_PADRAO):
    pasta = Path(pasta)
    if linhas <= 0 or colunas <= 0 or limite < 0:
        raise ValueError("dimensoes ou limite de transito invalidos")
    checksum = confere_log(pasta, linhas * colunas)
    stats = le_bloco(pasta)
    perfis = {u: le_perfil(pasta, u) for u in ("msgs", "flits")}
    totais = {}
    for unidade, contador in (("msgs", "packets"), ("flits", "flits")):
        matriz = perfis[unidade].matriz
        total = sum(map(sum, matriz))
        injetados = estatistica(stats, f"{REDE}.{contador}_injected::total")
        if total != injetados or any(v < 0 for linha in matriz for v in linha):
            raise ValueError(f"falha na conservacao de {unidade}")
        totais[unidade] = total

    perfil = perfis["flits"]
    num_routers = linhas * colunas
    mapa = perfil.roteador
    l1 = {n: r for n, r in mapa.items() if n.startswith("l1_cntrl")}
    if (
        set(l1) != {f"l1_cntrl{i}" for i in range(num_routers)}
        or sorted(l1.values()) != list(range(num_routers))
        or any(not 0 <= r < num_routers for r in mapa.values())
    ):
        raise ValueError("distribuicao dos controladores invalida no CSV")
    previsto = None
    if mapa_json is not None:
        dados = json.loads(Path(mapa_json).read_text())
        if (dados["linhas"], dados["colunas"]) != (linhas, colunas):
            raise ValueError("dimensoes do JSON nao correspondem a execucao")
        if dados["mapa"] != mapa:
            raise ValueError("mapa aplicado difere do JSON")
        previsto = dados["distancia_prevista"]
    elif any(l1[f"l1_cntrl{i}"] != i for i in range(num_routers)):
        raise ValueError("perfil sem JSON nao usou o mapa linear")

    medida = d_ponderada(perfil, mapa, colunas)
    custo = sum(
        peso * distancia(mapa[origem], mapa[destino], colunas)
        for origem, linha in zip(perfil.nomes, perfil.matriz)
        for destino, peso in zip(perfil.nomes, linha)
    )
    hops = estatistica(stats, f"{REDE}.average_hops")
    recebidos = estatistica(stats, f"{REDE}.flits_received::total")
    if recebidos <= 0 or recebidos != int(recebidos):
        raise ValueError("quantidade invalida de flits recebidos")
    confere_saltos(
        totais["flits"],
        int(recebidos),
        custo,
        hops,
        linhas + colunas - 2,
        limite,
    )

    ini = ConfigParser(interpolation=None)
    with (pasta / "config.ini").open() as arq:
        ini.read_file(arq)
    dominio = ini[REDE]["clk_domain"]
    periodo = int(ini[dominio]["clock"])
    ticks = int(estatistica(stats, "simTicks"))
    if periodo <= 0 or ticks <= 0:
        raise ValueError("periodo ou duracao da ROI invalidos")
    lat_rede = estatistica(stats, f"{REDE}.average_packet_network_latency")
    lat_fila = estatistica(stats, f"{REDE}.average_packet_queueing_latency")
    return {
        "distancia_prevista": previsto,
        "distancia_medida": medida,
        "average_hops": float(hops),
        "latencia_rede_ciclos": float(lat_rede / periodo),
        "latencia_fila_ciclos": float(lat_fila / periodo),
        "phi": fracao_l1_l1(perfil),
        "simTicks": ticks,
        "periodo_rede_ticks": periodo,
        "pacotes_injetados": totais["msgs"],
        "flits_injetados": totais["flits"],
        "flits_recebidos": int(recebidos),
        "limite_flits_transito": limite,
        "checksum": checksum,
    }


def escreve_csv(saida, linhas):
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    temporario = saida.with_name(saida.name + ".tmp")
    with temporario.open("w", newline="") as arq:
        writer = csv.DictWriter(arq, fieldnames=list(linhas[0]))
        writer.writeheader()
        writer.writerows(linhas)
    temporario.replace(saida)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("execucao", type=Path)
    ap.add_argument("--linhas", type=int, required=True)
    ap.add_argument("--colunas", type=int, required=True)
    ap.add_argument("--mapa", type=Path)
    ap.add_argument("--flits-transito", type=int, default=TRANSITO_PADRAO)
    args = ap.parse_args()
    try:
        linha = extrai(
            args.execucao,
            args.linhas,
            args.colunas,
            args.mapa,
            args.flits_transito,
        )
    except (OSError, ValueError, KeyError, IniError) as erro:
        ap.exit(1, f"{args.execucao}: {erro}\n")
    writer = csv.DictWriter(sys.stdout, fieldnames=list(linha))
    writer.writeheader()
    writer.writerow(linha)


if __name__ == "__main__":
    main()
