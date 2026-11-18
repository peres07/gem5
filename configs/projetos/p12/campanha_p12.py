# SPDX-License-Identifier: BSD-3-Clause
"""Executa a campanha P12 com 16 nucleos O3 e cinco mapas aleatorios."""

from extrai_p12 import grava_csv
from fluxo_p12 import PADROES, argumentos, avalia, mapeia, perfil, prepara
from mapeador_p12 import guloso
from matriz_p12 import le_perfil

FASES = {"vizinhanca": 20000, "dois_grupos": 20000, "uniforme": 5000}
POLITICAS = [("linear", 0), ("guloso", 0)] + [
    ("aleatorio", semente) for semente in (11, 22, 33, 44, 55)
]


def campanha(args):
    perfis = {}
    mapas = {}
    for padrao in PADROES:
        fases = args.fases or FASES[padrao]
        pasta = args.saida / padrao
        origem = pasta / "perfil"
        dados, referencia = perfil(args, origem, padrao, fases)
        perfis[padrao] = dados, referencia
        for politica, semente in POLITICAS:
            mapas[padrao, politica, semente] = mapeia(
                args, origem, dados, pasta / "mapas", politica, semente,
            )

    linhas = []
    for padrao in PADROES:
        fases = args.fases or FASES[padrao]
        dados, referencia = perfis[padrao]
        for politica, semente in POLITICAS:
            arquivo, mapa, previsto = mapas[padrao, politica, semente]
            pasta = args.saida / padrao / "avaliacoes" / arquivo.stem
            valores = avalia(
                args, pasta, padrao, fases, arquivo, mapa, previsto, referencia,
            )
            variacao, mesmo_mapa = "", ""
            if politica == "guloso":
                novo = le_perfil(pasta)
                ordem = [novo.nomes.index(nome) for nome in dados.nomes]
                variacao = sum(
                    abs(v - novo.matriz[ordem[i]][ordem[j]])
                    for i, linha in enumerate(dados.matriz)
                    for j, v in enumerate(linha)
                ) / sum(map(sum, dados.matriz))
                mesmo_mapa = guloso(novo, args.nucleos // 4, 4) == mapa
            linhas.append({
                "padrao": padrao, "nucleos": args.nucleos, "fases": fases,
                "linhas_msg": args.linhas_msg, "politica": politica,
                "semente_mapa": semente, "semente_carga": args.semente,
                **valores, "variacao_perfil": variacao,
                "mesmo_mapa_guloso": mesmo_mapa,
            })
    with (args.saida / "metricas.csv").open("w", newline="") as saida:
        grava_csv(saida, linhas)


if __name__ == "__main__":
    campanha(prepara(argumentos()))
