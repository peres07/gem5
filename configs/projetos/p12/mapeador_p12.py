"""Mapeamento linear, aleatorio, guloso e otimo para 8 L1."""

import argparse
import itertools
import json
import random
from pathlib import Path

from matriz_p12 import d_ponderada, distancia, le_perfil


def moveis_e_fixos(perfil):
    moveis = [n for n in perfil.nomes if n.startswith("l1_cntrl")]
    fixos = {n: perfil.roteador[n] for n in perfil.nomes if n not in moveis}
    return moveis, fixos


def _dados(perfil, linhas, colunas):
    moveis, fixos = moveis_e_fixos(perfil)
    if len(moveis) != linhas * colunas:
        raise ValueError("precisa haver uma L1 por roteador")
    if any(r < 0 or r >= linhas * colunas for r in fixos.values()):
        raise ValueError("roteador fixo fora da malha")
    idx = {n: i for i, n in enumerate(perfil.nomes)}
    fluxo = {
        (a, b): perfil.matriz[idx[a]][idx[b]] + perfil.matriz[idx[b]][idx[a]]
        for a in moveis for b in moveis if a != b
    }
    custo_fixo = {
        (a, r): sum(
            (perfil.matriz[idx[a]][idx[f]] + perfil.matriz[idx[f]][idx[a]])
            * distancia(r, rf, colunas)
            for f, rf in fixos.items()
        )
        for a in moveis for r in range(linhas * colunas)
    }
    return moveis, fixos, fluxo, custo_fixo


def linear(perfil, linhas, colunas, semente=None):
    moveis, fixos, _, _ = _dados(perfil, linhas, colunas)
    mapa = dict(fixos)
    for nome in moveis:
        i = int(nome.removeprefix("l1_cntrl"))
        if i >= linhas * colunas or i < 0:
            raise ValueError("indice da L1 fora da malha")
        mapa[nome] = i
    confere(mapa, moveis, linhas * colunas)
    return mapa


def aleatorio(perfil, linhas, colunas, semente):
    moveis, fixos, _, _ = _dados(perfil, linhas, colunas)
    posicoes = list(range(linhas * colunas))
    random.Random(semente).shuffle(posicoes)
    return fixos | dict(zip(moveis, posicoes))


def guloso(perfil, linhas, colunas, semente=None):
    moveis, fixos, fluxo, custo_fixo = _dados(perfil, linhas, colunas)
    mapa = dict(fixos)
    livres = set(range(linhas * colunas))
    restantes = set(moveis)
    total = {a: sum(fluxo[a, b] for b in moveis if b != a) for a in moveis}

    while restantes:
        colocados = [a for a in moveis if a not in restantes]
        escolhido = min(
            restantes,
            key=lambda a: (
                -sum(fluxo[a, b] for b in colocados),
                -total[a],
                int(a.removeprefix("l1_cntrl")),
            ),
        )
        pos = min(
            livres,
            key=lambda r: (
                custo_fixo[escolhido, r]
                + sum(fluxo[escolhido, b] * distancia(r, mapa[b], colunas)
                      for b in colocados),
                abs(r // colunas - (linhas - 1) / 2)
                + abs(r % colunas - (colunas - 1) / 2),
                r,
            ),
        )
        mapa[escolhido] = pos
        restantes.remove(escolhido)
        livres.remove(pos)

    # P12: trocas locais corrigem casos em que ocupar o centro cedo
    # deixa o segundo grupo espalhado; 16 L1 ainda e barato.
    def custo():
        return sum(custo_fixo[a, mapa[a]] for a in moveis) + sum(
            fluxo[a, b] * distancia(mapa[a], mapa[b], colunas)
            for i, a in enumerate(moveis) for b in moveis[:i]
        )

    atual = custo()
    while True:
        troca = None
        melhor = atual
        for i, a in enumerate(moveis):
            for b in moveis[:i]:
                mapa[a], mapa[b] = mapa[b], mapa[a]
                valor = custo()
                mapa[a], mapa[b] = mapa[b], mapa[a]
                if valor < melhor:
                    melhor, troca = valor, (a, b)
        if troca is None:
            break
        a, b = troca
        mapa[a], mapa[b] = mapa[b], mapa[a]
        atual = melhor
    return mapa


def otimo(perfil, linhas, colunas, semente=None):
    moveis, fixos, fluxo, custo_fixo = _dados(perfil, linhas, colunas)
    if len(moveis) > 8:
        raise ValueError("forca bruta limitada a 8 L1")
    melhor = None
    melhor_custo = None
    for perm in itertools.permutations(range(len(moveis))):
        custo = sum(custo_fixo[a, perm[i]] for i, a in enumerate(moveis))
        custo += sum(
            fluxo[a, b] * distancia(perm[i], perm[j], colunas)
            for i, a in enumerate(moveis)
            for j, b in enumerate(moveis[:i])
        )
        if melhor_custo is None or custo < melhor_custo:
            melhor, melhor_custo = perm, custo
    return fixos | dict(zip(moveis, melhor))


def confere(mapa, moveis, roteadores):
    if set(moveis) - set(mapa):
        raise ValueError("mapa incompleto")
    posicoes = [mapa[n] for n in moveis]
    if sorted(posicoes) != list(range(roteadores)):
        raise ValueError("cada roteador precisa receber uma L1")


POLITICAS = {"linear": linear, "aleatorio": aleatorio,
            "guloso": guloso, "otimo": otimo}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--perfil", required=True)
    ap.add_argument("--politica", choices=POLITICAS, required=True)
    ap.add_argument("--linhas", type=int, required=True)
    ap.add_argument("--colunas", type=int, required=True)
    ap.add_argument("--semente", type=int, default=1)
    ap.add_argument("--unidade", choices=("flits", "msgs"), default="flits")
    ap.add_argument("--saida", required=True)
    args = ap.parse_args()
    perfil = le_perfil(args.perfil, args.unidade)
    mapa = POLITICAS[args.politica](perfil, args.linhas, args.colunas,
                                    args.semente)
    moveis, _ = moveis_e_fixos(perfil)
    confere(mapa, moveis, args.linhas * args.colunas)
    try:
        custo = d_ponderada(perfil, mapa, args.colunas)
    except ValueError:
        custo = None
    saida = {"mapa": mapa, "politica": args.politica,
             "semente": args.semente, "perfil": str(Path(args.perfil).resolve()),
             "linhas": args.linhas, "colunas": args.colunas,
             "unidade": args.unidade, "distancia_prevista": custo}
    Path(args.saida).write_text(json.dumps(saida, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
