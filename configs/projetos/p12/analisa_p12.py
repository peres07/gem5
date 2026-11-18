# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Gera os quatro graficos da campanha (requer matplotlib)."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import (
    mean,
    stdev,
)

from campanha_p12 import (
    PERTURBACOES,
    politicas,
)
from fluxo_p12 import (
    MALHAS,
    PROGRAMAS,
)

POLITICAS = ("linear", "guloso", "aleatorio", "otimo")


def agrega(arq):
    """Resume os sorteios aleatorios dentro de cada semente de perturbacao."""
    casos = defaultdict(dict)
    for linha in csv.DictReader(arq):
        if linha["unidade_mapa"] != "flits":
            raise ValueError("a campanha principal deve usar mapas de flits")
        caso = linha["programa"], int(linha["nucleos"])
        chave = (
            linha["politica"],
            int(linha["semente_mapa"]),
            int(linha["semente_perturbacao"]),
        )
        if chave in casos[caso]:
            raise ValueError(f"avaliacao duplicada: {caso}, {chave}")
        casos[caso][chave] = linha
    if not casos:
        raise ValueError("CSV sem avaliacoes")

    for (programa, n), avaliacoes in sorted(casos.items()):
        esperado = {(p, m, s) for p, m in politicas(n) for s in PERTURBACOES}
        if esperado != set(avaliacoes):
            raise ValueError(
                f"campanha incompleta ou inesperada: {programa}-{n}"
            )
        for politica in dict.fromkeys(p for p, _ in politicas(n)):
            sementes = [m for p, m in politicas(n) if p == politica]

            def pares(metrica):
                for s in PERTURBACOES:
                    base = float(avaliacoes["linear", 0, s][metrica])
                    valor = mean(
                        float(avaliacoes[politica, m, s][metrica])
                        for m in sementes
                    )
                    yield valor, base

            tempo = [v / base for v, base in pares("simTicks")]
            yield {
                "programa": programa,
                "nucleos": n,
                "politica": politica,
                "distancia_prevista": mean(
                    v for v, _ in pares("distancia_prevista")
                ),
                "distancia_medida": mean(
                    v for v, _ in pares("distancia_medida")
                ),
                "latencia": mean(v for v, _ in pares("latencia_rede_ciclos")),
                "tempo": mean(tempo),
                "erro_padrao": stdev(tempo) / len(tempo) ** 0.5,
                "reducao_tempo": 100 * (1 - mean(tempo)),
                "reducao_saltos": 100
                * mean(1 - v / base for v, base in pares("average_hops")),
            }


def graficos(linhas, pasta):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    # Quantil bilateral de Student para as tres sementes fixas da campanha.
    critico = 4.302652729696142  # t(0.975, df=2)
    pasta.mkdir(parents=True, exist_ok=True)
    indices = {p: i for i, p in enumerate(POLITICAS)}
    for metrica, nome, y in (
        ("distancia_medida", "distancia", "Distância ponderada (saltos)"),
        ("latencia", "latencia", "Latência média de rede (ciclos)"),
        ("tempo", "tempo", "Tempo relativo ao linear (IC 95% pareado)"),
    ):
        fig, eixos = plt.subplots(
            1, len(PROGRAMAS), figsize=(13, 4), sharey=True
        )
        for prog, ax in zip(PROGRAMAS, eixos):
            for i, (n, (rows, cols)) in enumerate(MALHAS.items()):
                dados = [
                    r
                    for r in linhas
                    if r["programa"] == prog and r["nucleos"] == n
                ]
                if not dados:
                    continue
                x = [indices[r["politica"]] + (i - 0.5) * 0.36 for r in dados]
                ax.bar(
                    x,
                    [r[metrica] for r in dados],
                    width=0.36,
                    label=f"{rows}×{cols}",
                    yerr=(
                        [critico * r["erro_padrao"] for r in dados]
                        if metrica == "tempo"
                        else None
                    ),
                )
                if metrica == "distancia_medida":
                    ax.scatter(
                        x,
                        [r["distancia_prevista"] for r in dados],
                        marker="_",
                        color="black",
                        zorder=3,
                    )
            ax.set_title(prog)
            ax.set_xticks(list(indices.values()), POLITICAS)
            ax.tick_params(axis="x", labelrotation=25)
            if metrica == "tempo":
                ax.axhline(1, color="black", linestyle=":")
            if ax.get_legend_handles_labels()[0]:
                ax.legend()
        eixos[0].set_ylabel(y)
        if metrica == "distancia_medida":
            fig.suptitle("Barras: medida; traços pretos: previsão do perfil")
        fig.savefig(pasta / f"{nome}.png", bbox_inches="tight")
        plt.close(fig)

    fig, ax = plt.subplots(layout="constrained")
    for programa in PROGRAMAS:
        dados = [r for r in linhas if r["programa"] == programa]
        if dados:
            ax.scatter(
                [r["reducao_saltos"] for r in dados],
                [r["reducao_tempo"] for r in dados],
                label=programa,
            )
    ax.set(xlabel="Redução de saltos (%)", ylabel="Redução de tempo (%)")
    ax.axhline(0, color="black", linestyle=":")
    ax.axvline(0, color="black", linestyle=":")
    ax.legend()
    fig.savefig(pasta / "saltos_tempo.png")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("metricas", type=Path)
    ap.add_argument("--saida", type=Path, required=True)
    args = ap.parse_args()
    try:
        with args.metricas.open(newline="") as arq:
            linhas = list(agrega(arq))
        graficos(linhas, args.saida)
    except (
        ImportError,
        OSError,
        ValueError,
        KeyError,
        ZeroDivisionError,
    ) as erro:
        ap.exit(1, f"{erro}\n")


if __name__ == "__main__":
    main()
