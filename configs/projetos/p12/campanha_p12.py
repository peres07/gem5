# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Campanha fatorial em duas passadas, com retomada de execucoes validas."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from extrai_p12 import escreve_csv
from fluxo_p12 import (
    ERROS_DADOS,
    MALHAS,
    PROGRAMAS,
    adiciona_opcoes,
    configura,
)
from mapeador_p12 import (
    cria_mapa,
    linear,
)
from matriz_p12 import (
    d_ponderada,
    le_perfil,
)

MAPAS = (
    ("linear", 0),
    ("guloso", 0),
    ("aleatorio", 1),
    ("aleatorio", 2),
    ("aleatorio", 3),
)
PERTURBACOES = (11, 12, 13)


def politicas(nucleos):
    return MAPAS + (("otimo", 0),) if nucleos == 8 else MAPAS


def passada_perfis(pool, fluxo, casos, semente):
    def prepara(caso):
        prog, nucleos = caso
        perfil = fluxo.perfil(prog, nucleos, semente)
        for politica, semente_mapa in politicas(nucleos):
            fluxo.mapeia(perfil, politica, semente_mapa, nucleos)

    list(pool.map(prepara, casos))


def mapas_prontos(fluxo, casos, semente):
    for prog, nucleos in casos:
        perfil = fluxo.perfil(prog, nucleos, semente, executar=False)
        assinatura = fluxo.assinatura_perfil(perfil)
        for politica, semente_mapa in politicas(nucleos):
            mapa = (
                fluxo.saida
                / "mapas"
                / (f"{perfil.name}-{politica}-{semente_mapa}-flits.json")
            )
            dados = json.loads(mapa.read_text())
            if (
                dados["perfil_sha256"] != assinatura
                or dados["perfil"] != str(perfil.resolve())
                or (dados["linhas"], dados["colunas"]) != MALHAS[nucleos]
                or dados["politica"] != politica
                or dados["semente"] != semente_mapa
                or dados["unidade"] != "flits"
            ):
                raise ValueError(
                    f"mapa desatualizado: {mapa}; refaca os perfis"
                )
            yield prog, nucleos, mapa


def passada_avaliacoes(pool, fluxo, mapas):
    tarefas = [(*caso, semente) for caso in mapas for semente in PERTURBACOES]

    def avalia(tarefa):
        return fluxo.avalia(*tarefa)

    return list(pool.map(avalia, tarefas))


def estabilidade(pool, fluxo, mapas, semente):
    def compara(caso):
        prog, nucleos, mapa = caso
        dados = json.loads(mapa.read_text())
        pasta = fluxo.saida / "estabilidade" / f"{prog}-{nucleos}"
        fluxo.roda(pasta, prog, nucleos, semente, mapa)
        linear = le_perfil(dados["perfil"])
        guloso = le_perfil(pasta)
        if set(linear.nomes) != set(guloso.nomes):
            raise ValueError(f"controladores diferentes: {pasta}")
        indices = {nome: i for i, nome in enumerate(guloso.nomes)}
        ordem = [indices[nome] for nome in linear.nomes]
        diferenca = sum(
            abs(peso - guloso.matriz[ordem[i]][ordem[j]])
            for i, linha in enumerate(linear.matriz)
            for j, peso in enumerate(linha)
        )
        segundo = cria_mapa(pasta, "guloso", *MALHAS[nucleos], 0, "flits")
        return {
            "programa": prog,
            "nucleos": nucleos,
            "semente_perfil": semente,
            "diferenca_relativa": diferenca / sum(map(sum, linear.matriz)),
            "mesmo_mapa": segundo["mapa"] == dados["mapa"],
        }

    gulosos = [
        caso for caso in mapas if caso[2].stem.endswith("-guloso-0-flits")
    ]
    return list(pool.map(compara, gulosos))


def referencias(mapas):
    """Compara mapas na mesma matriz do perfil (fixos nunca se movem)."""
    custos = {}
    perfis = {}
    for prog, n, mapa in mapas:
        dados = json.loads(mapa.read_text())
        chave = prog, n
        custos.setdefault(chave, {})[dados["politica"], dados["semente"]] = (
            dados["distancia_prevista"]
        )
        perfis[chave] = dados["perfil"]
    for (prog, n), valores in sorted(custos.items()):
        linhas, colunas = MALHAS[n]
        perfil = perfis[prog, n]
        guloso_msgs = cria_mapa(perfil, "guloso", linhas, colunas, 0, "msgs")
        guloso_flits = cria_mapa(perfil, "guloso", linhas, colunas, 0, "flits")
        dados = {
            "programa": prog,
            "nucleos": n,
            "d_linear": valores["linear", 0],
            "d_guloso": valores["guloso", 0],
            "d_aleatorio_media": sum(
                valores["aleatorio", s] for s in (1, 2, 3)
            )
            / 3,
            "d_otimo": valores.get(("otimo", 0)),
            "d_serpentina": None,
            "d_hamiltoniano": None,
            "mesmo_guloso_msgs_flits": guloso_msgs["mapa"]
            == guloso_flits["mapa"],
        }
        if prog == "vizinhanca" and n == 16:
            p = le_perfil(perfil)
            base = linear(p, linhas, colunas)
            for nome, ordem in (
                (
                    "serpentina",
                    (0, 1, 2, 3, 7, 6, 5, 4, 8, 9, 10, 11, 15, 14, 13, 12),
                ),
                (
                    "hamiltoniano",
                    (0, 1, 2, 3, 7, 11, 15, 14, 10, 6, 5, 9, 13, 12, 8, 4),
                ),
            ):
                mapa = base | {f"l1_cntrl{i}": r for i, r in enumerate(ordem)}
                dados[f"d_{nome}"] = d_ponderada(p, mapa, colunas)
        yield dados


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    adiciona_opcoes(ap)
    ap.add_argument(
        "--fase", choices=("perfis", "avaliacoes", "todas"), default="todas"
    )
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--programa", choices=PROGRAMAS, action="append")
    ap.add_argument("--nucleos", type=int, choices=MALHAS, action="append")
    ap.add_argument(
        "--estabilidade",
        action="store_true",
        help="gera tambem o segundo perfil (mapa guloso)",
    )
    ap.add_argument(
        "--listar",
        action="store_true",
        help="mostra as quantidades sem executar o simulador",
    )
    args = ap.parse_args()
    fluxo = configura(ap, args)
    if args.jobs < 1:
        ap.error("--jobs deve ser positivo")
    if args.semente_perfil in PERTURBACOES:
        ap.error("semente do perfil deve diferir das sementes de avaliacao")
    if args.estabilidade and args.fase == "perfis":
        ap.error("--estabilidade requer --fase avaliacoes ou todas")
    casos = [
        (prog, n)
        for prog in PROGRAMAS
        for n in MALHAS
        if (not args.programa or prog in args.programa)
        and (not args.nucleos or n in args.nucleos)
    ]
    n_avaliacoes = sum(len(politicas(n)) for _, n in casos) * len(PERTURBACOES)
    print(f"{len(casos)} perfis; {n_avaliacoes} avaliacoes", flush=True)
    if args.listar:
        return
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            if args.fase in ("perfis", "todas"):
                passada_perfis(pool, fluxo, casos, args.semente_perfil)
            if args.fase in ("avaliacoes", "todas"):
                mapas = list(mapas_prontos(fluxo, casos, args.semente_perfil))
                escreve_csv(
                    fluxo.saida / "referencias.csv", list(referencias(mapas))
                )
                linhas = passada_avaliacoes(pool, fluxo, mapas)
                escreve_csv(fluxo.saida / "metricas.csv", linhas)
                if args.estabilidade:
                    linhas = estabilidade(
                        pool, fluxo, mapas, args.semente_perfil
                    )
                    escreve_csv(fluxo.saida / "estabilidade.csv", linhas)
    except ERROS_DADOS as erro:
        ap.exit(1, f"{erro}\n")


if __name__ == "__main__":
    main()
