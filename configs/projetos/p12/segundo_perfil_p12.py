# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Avalia o mapa guloso recalculado a partir do perfil de estabilidade."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from campanha_p12 import (
    PERTURBACOES,
    mapas_prontos,
)
from extrai_p12 import escreve_csv
from fluxo_p12 import (
    ERROS_DADOS,
    MALHAS,
    PROGRAMAS,
    adiciona_opcoes,
    configura,
)


def prepara(fluxo, segundo, semente):
    casos = [(prog, n) for prog in PROGRAMAS for n in MALHAS]
    for prog, n, mapa in mapas_prontos(fluxo, casos, semente):
        if json.loads(mapa.read_text())["politica"] != "guloso":
            continue
        perfil = fluxo.saida / "estabilidade" / f"{prog}-{n}"
        fluxo.roda(perfil, prog, n, semente, mapa, executar=False)
        novo = segundo.mapeia(perfil, "guloso", 0, n)
        for perturbacao in PERTURBACOES:
            pasta = (
                fluxo.saida
                / "avaliacao"
                / mapa.stem
                / f"perturb-{perturbacao}"
            )
            base = fluxo.roda(
                pasta, prog, n, perturbacao, mapa, executar=False
            )
            yield prog, n, novo, perturbacao, base


def compara(linha, base):
    for campo in ("checksum", "periodo_rede_ticks"):
        if linha[campo] != base[campo]:
            raise ValueError(
                f"{campo} difere do primeiro guloso: {linha['execucao']}"
            )
    ticks = base["simTicks"]
    return {
        **linha,
        "simTicks_primeiro_guloso": ticks,
        "reducao_tempo_vs_primeiro_guloso_pct": (
            100 * (1 - linha["simTicks"] / ticks)
        ),
    }


def executa(fluxo, semente, jobs):
    segundo = replace(fluxo, saida=fluxo.saida / "segundo-perfil")
    tarefas = list(prepara(fluxo, segundo, semente))
    total = len(PROGRAMAS) * len(MALHAS) * len(PERTURBACOES)
    if len(tarefas) != total:
        raise ValueError(f"esperava {total} avaliações do segundo guloso")

    def avalia(tarefa):
        prog, n, mapa, perturbacao, base = tarefa
        return compara(segundo.avalia(prog, n, mapa, perturbacao), base)

    print(f"{total} avaliações do segundo perfil", flush=True)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        linhas = list(pool.map(avalia, tarefas))
    csv = fluxo.saida / "segundo-perfil.csv"
    escreve_csv(csv, linhas)
    return csv


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    adiciona_opcoes(ap)
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()
    fluxo = configura(ap, args)
    if args.jobs < 1:
        ap.error("--jobs deve ser positivo")
    if args.semente_perfil in PERTURBACOES:
        ap.error("semente do perfil deve diferir das sementes de avaliacao")
    try:
        print(executa(fluxo, args.semente_perfil, args.jobs))
    except ERROS_DADOS as erro:
        ap.exit(1, f"{erro}\n")


if __name__ == "__main__":
    main()
