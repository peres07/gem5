# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Confere e resume os CSVs da campanha C++ sem executar o gem5."""

import argparse
import csv
import json
from collections import defaultdict
from math import isclose, isfinite, sqrt
from pathlib import Path
from statistics import mean, stdev

from campanha_p12 import PERTURBACOES, politicas
from extrai_p12 import escreve_csv
from fluxo_p12 import (
    ERROS_DADOS,
    MALHAS,
    PROGRAMAS,
    ROOT,
    Fluxo,
)
from mapeador_p12 import confere, moveis_e_fixos
from matriz_p12 import d_ponderada, distancia, fracao_l1_l1, le_perfil

METRICAS = (
    "distancia_medida",
    "average_hops",
    "latencia_rede_ciclos",
    "latencia_fila_ciclos",
    "simTicks",
)
ROTULOS = dict(
    zip(METRICAS, ("Distância", "Saltos", "Lat. rede", "Lat. fila", "Tempo"))
)


def reducao(base, valor):
    return 100 * (1 - valor / base) if base else None


def atribuicao_minima(custos):
    """Atribui uma L1 por roteador, ignorando o custo entre duas L1."""
    n = len(custos)
    dp = [0] * (1 << n)
    for mascara in range(1, 1 << n):
        custo = custos[mascara.bit_count() - 1]
        opcoes = mascara
        melhor = None
        while opcoes:
            bit = opcoes & -opcoes
            valor = dp[mascara ^ bit] + custo[bit.bit_length() - 1]
            melhor = valor if melhor is None else min(melhor, valor)
            opcoes ^= bit
        dp[mascara] = melhor
    return dp[-1]


def limites_perfil(perfil, linhas, colunas):
    """Limites inferiores de D e E[D] sob permutacao uniforme das L1."""
    moveis, fixos = moveis_e_fixos(perfil)
    n = linhas * colunas
    if set(moveis) != {f"l1_cntrl{i}" for i in range(n)} or n < 2:
        raise ValueError("o perfil deve ter uma L1 por roteador")
    if any(not 0 <= r < n for r in fixos.values()):
        raise ValueError("roteador fixo fora da malha")
    idx = {nome: i for i, nome in enumerate(perfil.nomes)}
    matriz = perfil.matriz
    total = sum(map(sum, matriz))
    if total <= 0 or any(p < 0 for linha in matriz for p in linha):
        raise ValueError("matriz vazia ou com pesos negativos")

    def peso(a, b):
        return matriz[idx[a]][idx[b]]

    dist = [[distancia(r, s, colunas) for s in range(n)] for r in range(n)]
    ff = sum(
        peso(a, b) * dist[r][s]
        for a, r in fixos.items()
        for b, s in fixos.items()
    )
    mf = [
        [
            sum((peso(a, b) + peso(b, a)) * dist[r][s]
                for b, s in fixos.items())
            for r in range(n)
        ]
        for a in moveis
    ]
    mm = [
        peso(a, b) + peso(b, a)
        for i, a in enumerate(moveis)
        for b in moveis[:i]
    ]
    ds = [dist[r][s] for r in range(n) for s in range(r)]
    # Toda permutacao usa o mesmo multiconjunto de distancias entre pares.
    # Parear os maiores pesos com distancias menores relaxa a geometria.
    mm_min = sum(w * d for w, d in zip(sorted(mm, reverse=True), sorted(ds)))
    # Marginais: uma L1 uniforme; duas L1 distintas sem reposicao.
    e_mm = sum(mm) * mean(ds)
    e_mf = sum(map(sum, mf)) / n
    return {
        "flits_perfil": total,
        "phi_perfil": fracao_l1_l1(perfil),
        "d_min_relaxado": (ff + sum(mm) + sum(map(min, mf))) / total,
        "d_min_atribuicao": (ff + mm_min + atribuicao_minima(mf)) / total,
        "d_aleatorio_l1_l1": e_mm / total,
        "d_aleatorio_l1_fixo": e_mf / total,
        "d_aleatorio_fixo_fixo": ff / total,
        "d_aleatorio_esperado": (ff + e_mm + e_mf) / total,
    }


def linhas_csv(caminho):
    with caminho.open(newline="") as arq:
        yield from csv.DictReader(arq)


def chave_caso(linha):
    programa, n = linha["programa"], int(linha["nucleos"])
    if programa not in PROGRAMAS or n not in MALHAS:
        raise ValueError(f"caso fora da campanha C++: {programa}-{n}")
    return programa, n


def le_avaliacoes(caminho, segundo=False):
    casos = defaultdict(dict)
    for linha in linhas_csv(caminho):
        programa, n = chave_caso(linha)
        if (
            MALHAS[n] != (int(linha["linhas"]), int(linha["colunas"]))
            or linha["unidade_mapa"] != "flits"
            or linha.get("carga", "cpp") != "cpp"
            or linha.get("aquecimento_rapido", "False") != "False"
        ):
            raise ValueError(f"avaliacao fora da campanha C++: {linha}")
        chave = (
            linha["politica"],
            int(linha["semente_mapa"]),
            int(linha["semente_perturbacao"]),
        )
        if chave in casos[programa, n]:
            raise ValueError(f"avaliacao duplicada: {programa}-{n} {chave}")
        for metrica in (*METRICAS, "distancia_prevista"):
            valor(linha, metrica)
        casos[programa, n][chave] = linha
    if not casos:
        raise ValueError(f"{caminho} sem avaliacoes")
    for (programa, n), avaliacoes in casos.items():
        ps = (("guloso", 0),) if segundo else politicas(n)
        esperado = {(p, m, s) for p, m in ps for s in PERTURBACOES}
        if set(avaliacoes) != esperado:
            raise ValueError(
                f"campanha incompleta ou inesperada: {programa}-{n}"
            )
    return casos


def le_por_caso(caminho, casos):
    dados = {}
    for linha in linhas_csv(caminho):
        caso = chave_caso(linha)
        if caso in dados:
            raise ValueError(f"caso duplicado em {caminho}: {caso}")
        dados[caso] = linha
    if dados.keys() != casos.keys():
        raise ValueError(f"casos divergentes em {caminho}")
    return dados


def carrega_mapa(campanha, pasta, perfil, dimensoes, politica, semente):
    nome = f"{pasta.name}-{politica}-{semente}-flits.json"
    caminho = campanha / "mapas" / nome
    dados = json.loads(caminho.read_text())
    mapa = dados["mapa"]
    moveis, fixos = moveis_e_fixos(perfil)
    confere(mapa, moveis, len(moveis))
    d = d_ponderada(perfil, mapa, dimensoes[1])
    if (
        dados["perfil_sha256"] != Fluxo.assinatura_perfil(pasta)
        or (dados["linhas"], dados["colunas"]) != dimensoes
        or dados["politica"] != politica
        or dados["semente"] != semente
        or dados["unidade"] != "flits"
        or set(mapa) != set(perfil.nomes)
        or any(mapa[n] != r for n, r in fixos.items())
        or not isclose(d, dados["distancia_prevista"], abs_tol=1e-12)
    ):
        raise ValueError(f"mapa incompatível com o perfil: {caminho}")
    return caminho, mapa, d


def valor(linha, metrica):
    x = float(linha[metrica])
    if not isfinite(x) or x < 0 or (metrica == "simTicks" and x == 0):
        raise ValueError(f"métrica inválida: {metrica}={x}")
    return x


def resumo_pareado(pares):
    """IC t bilateral de 95% das reducoes, com tres sementes pareadas."""
    pares = list(pares)
    if len(pares) != 3:
        raise ValueError("o IC requer as tres sementes da campanha")

    def intervalo(dados):
        media = mean(dados)
        margem = 4.302652729696142 * stdev(dados) / sqrt(len(dados))
        return media, media - margem, media + margem

    absoluto = intervalo([a - b for a, b in pares])
    relativo = (
        intervalo([reducao(a, b) for a, b in pares])
        if all(a for a, _ in pares)
        else (None, None, None)
    )
    return {
        "n_pares": len(pares),
        "media_base": mean(a for a, _ in pares),
        "media_candidato": mean(b for _, b in pares),
        "delta": absoluto[0],
        "delta_ic95_inf": absoluto[1],
        "delta_ic95_sup": absoluto[2],
        "reducao_pct": relativo[0],
        "ic95_inf_pct": relativo[1],
        "ic95_sup_pct": relativo[2],
    }


def compara(avaliacoes, politica, metrica, base="linear"):
    sementes = (1, 2, 3) if politica == "aleatorio" else (0,)
    # Os tres mapas sorteados sao agregados dentro de cada perturbacao.
    # O IC de aleatorio e condicional a esses mapas, nao usa n=9.
    return resumo_pareado(
        (
            valor(avaliacoes[base, 0, s], metrica),
            mean(valor(avaliacoes[politica, m, s], metrica) for m in sementes),
        )
        for s in PERTURBACOES
    )


def previsoes(avaliacoes):
    por_mapa = defaultdict(list)
    for (p, m, _), linha in avaliacoes.items():
        por_mapa[p, m].append(valor(linha, "distancia_prevista"))
    for chave, ds in por_mapa.items():
        if not isclose(min(ds), max(ds), rel_tol=1e-12):
            raise ValueError(f"previsao mudou entre perturbacoes: {chave}")
    return {chave: mean(ds) for chave, ds in por_mapa.items()}


def resumo_distancias(ident, avaliacoes, referencia):
    ds = previsoes(avaliacoes)
    for politica, coluna in (
        ("linear", "d_linear"),
        ("guloso", "d_guloso"),
        ("aleatorio", "d_aleatorio_media"),
        ("otimo", "d_otimo"),
    ):
        custos = [d for (p, _), d in ds.items() if p == politica]
        informado = referencia[coluna]
        confere = (
            isclose(mean(custos), float(informado), rel_tol=1e-9)
            if custos else not informado
        )
        if not confere:
            raise ValueError(f"referencia divergente: {ident}, {coluna}")
    for politica in dict.fromkeys(p for p, _ in ds):
        linhas = [r for (p, _, _), r in avaliacoes.items() if p == politica]
        previsto = mean(d for (p, _), d in ds.items() if p == politica)
        dist = mean(valor(r, "distancia_medida") for r in linhas)
        hops = mean(valor(r, "average_hops") for r in linhas)
        yield {
            **ident,
            "politica": politica,
            "n_avaliacoes": len(linhas),
            "d_prevista": previsto,
            "d_medida": dist,
            "hops_medidos": hops,
            "d_medida_menos_prevista": dist - previsto,
            "hops_menos_d_medida": hops - dist,
            "reducao_prevista_pct": reducao(ds["linear", 0], previsto),
            "reducao_hops_medida_pct": compara(
                avaliacoes, politica, "average_hops"
            )["reducao_pct"],
        }


def resumo_otimo(ident, avaliacoes, referencia):
    d_g = valor(referencia, "d_guloso")
    d_o = valor(referencia, "d_otimo")
    d_l = valor(referencia, "d_linear")
    if d_o > min(d_g, d_l, valor(referencia, "d_aleatorio_media")) + 1e-12:
        raise ValueError(f"custo otimo inconsistente: {ident}")
    medido = compara(avaliacoes, "otimo", "average_hops", base="guloso")
    return {
        **ident,
        "d_guloso": d_g,
        "d_otimo": d_o,
        "gap_saltos_por_flit": d_g - d_o,
        "gap_pct_do_otimo": -reducao(d_o, d_g) if d_o else None,
        "teto_reducao_perfil_pct": reducao(d_l, d_o),
        "reducao_hops_guloso_vs_linear_pct": compara(
            avaliacoes, "guloso", "average_hops"
        )["reducao_pct"],
        "reducao_hops_otimo_vs_linear_pct": compara(
            avaliacoes, "otimo", "average_hops"
        )["reducao_pct"],
        "hops_guloso_medido": medido["media_base"],
        "hops_otimo_medido": medido["media_candidato"],
        "reducao_hops_otimo_vs_guloso_pct": medido["reducao_pct"],
    }


def resumo_segundo(ident, primeiro, segundo):
    d1 = previsoes(primeiro)["guloso", 0]
    d2 = previsoes(segundo)["guloso", 0]
    pares = [
        (primeiro["guloso", 0, s], segundo["guloso", 0, s])
        for s in PERTURBACOES
    ]
    for base, novo in pares:
        for coluna in ("checksum", "periodo_rede_ticks"):
            if int(base[coluna]) != int(novo[coluna]):
                raise ValueError(f"pares incompatíveis: {ident}, {coluna}")
    for metrica in METRICAS:
        yield {
            **ident,
            "metrica": metrica,
            # As duas previsoes usam matrizes diferentes: nao subtrair.
            "d_prevista_perfil_linear": d1,
            "d_prevista_perfil_guloso": d2,
            **resumo_pareado(
                (valor(a, metrica), valor(b, metrica)) for a, b in pares
            ),
        }


def analisa_caso(campanha, caso, avaliacoes):
    programa, n = caso
    pasta = campanha / "perfil" / f"{programa}-{n}"
    perfil = le_perfil(pasta)
    dimensoes = MALHAS[n]
    mapas = {
        (p, s): carrega_mapa(campanha, pasta, perfil, dimensoes, p, s)
        for p, s in politicas(n)
    }
    _, _, d_g = mapas["guloso", 0]
    _, mapa_l, d_l = mapas["linear", 0]
    if perfil.roteador != mapa_l:
        raise ValueError(f"o perfil nao usou o mapa linear: {pasta}")
    for (p, m, _), linha in avaliacoes.items():
        if not isclose(valor(linha, "distancia_prevista"), mapas[p, m][2]):
            raise ValueError(f"metricas.csv incompatível com mapas: {caso}")
    limites = limites_perfil(perfil, *dimensoes)
    d_o = mapas["otimo", 0][2] if n == 8 else None
    d_min = limites["d_min_atribuicao"] if d_o is None else d_o
    if d_min > min(v[2] for v in mapas.values()) + 1e-12:
        raise ValueError(f"limite incompatível com mapa candidato: {caso}")
    d_a = mean(mapas["aleatorio", s][2] for s in (1, 2, 3))
    ident = {"programa": programa, "nucleos": n}
    return {
        **ident,
        **limites,
        "d_linear": d_l,
        "d_guloso": d_g,
        "d_otimo": d_o,
        "d_min_usado": d_min,
        "tipo_teto": "exato" if d_o is not None else "relaxado",
        "teto_reducao_pct": reducao(d_l, d_min),
        "teto_simples_pct": reducao(d_l, limites["d_min_relaxado"]),
        "reducao_guloso_prevista_pct": reducao(d_l, d_g),
        "reducao_guloso_d_medida_pct": compara(
            avaliacoes, "guloso", "distancia_medida"
        )["reducao_pct"],
        "reducao_guloso_hops_medida_pct": compara(
            avaliacoes, "guloso", "average_hops"
        )["reducao_pct"],
        "d_aleatorio_tres_mapas": d_a,
        "delta_aleatorio_observado_menos_esperado": (
            d_a - limites["d_aleatorio_esperado"]
        ),
    }


def confere_campanha(pasta, matrizes=None, arquivo_segundo=None):
    original = (pasta / "cpp-metricas.csv").exists()
    prefixo = "cpp-" if original else ""

    def arquivo(nome):
        return pasta / f"{prefixo}{nome}.csv"

    primeiro = le_avaliacoes(arquivo("metricas"))
    casos_esperados = {(p, n) for p in PROGRAMAS for n in MALHAS}
    if original and set(primeiro) != casos_esperados:
        raise ValueError("faltam casos na campanha original")
    refs = le_por_caso(arquivo("referencias"), primeiro)
    estabilidade = le_por_caso(arquivo("estabilidade"), primeiro)
    caminho = arquivo_segundo or arquivo("segundo-perfil")
    segundo = {}
    if original or arquivo_segundo is not None or caminho.exists():
        segundo = le_avaliacoes(caminho, segundo=True)
        if primeiro.keys() != segundo.keys():
            raise ValueError(f"casos divergentes em {caminho}")

    tabelas = defaultdict(list)
    for caso, avaliacoes in sorted(primeiro.items()):
        programa, n = caso
        ident = {"programa": programa, "nucleos": n}
        tabelas["real_vs_previsto"].extend(
            resumo_distancias(ident, avaliacoes, refs[caso])
        )
        if n == 8:
            tabelas["guloso_vs_otimo"].append(
                resumo_otimo(ident, avaliacoes, refs[caso])
            )
        if programa == "uniforme":
            for politica in dict.fromkeys(p for p, _ in politicas(n)):
                if politica == "linear":
                    continue
                for metrica in METRICAS:
                    tabelas["uniforme_ic95"].append({
                        **ident,
                        "politica": politica,
                        "metrica": metrica,
                        **compara(avaliacoes, politica, metrica),
                    })
        e = estabilidade[caso]
        if e["mesmo_mapa"] not in ("False", "True"):
            raise ValueError(f"mesmo_mapa invalido: {caso}")
        igual_msg_flit = refs[caso]["mesmo_guloso_msgs_flits"]
        if igual_msg_flit not in ("False", "True"):
            raise ValueError(f"mesmo_guloso_msgs_flits invalido: {caso}")
        tabelas["estabilidade_perfil"].append({
            **ident,
            "semente_perfil": int(e["semente_perfil"]),
            "diferenca_trafego_pct": 100 * valor(e, "diferenca_relativa"),
            "mesmo_mapa": e["mesmo_mapa"] == "True",
            "mesmo_mapa_msgs_flits": igual_msg_flit == "True",
            "segundo_avaliado": caso in segundo,
        })
        if caso in segundo:
            tabelas["segundo_perfil_ic95"].extend(
                resumo_segundo(ident, avaliacoes, segundo[caso])
            )
        if matrizes is not None:
            tabelas["perfil_com_matrizes"].append(
                analisa_caso(matrizes, caso, avaliacoes)
            )
    return tabelas


def mostra(tabelas):
    def num(x):
        return "n/d" if x is None else f"{x:+.3f}"

    print("Programa/núcleos  Mapa       D prevista  D medida  Hops medidos")
    for r in tabelas["real_vs_previsto"]:
        caso = f"{r['programa']}/{r['nucleos']}"
        print(f"{caso:17} {r['politica']:10} {r['d_prevista']:9.4f}  "
              f"{r['d_medida']:8.4f}  {r['hops_medidos']:12.4f}")
    for r in tabelas.get("guloso_vs_otimo", []):
        print(f"{r['programa']}/8 guloso − ótimo: "
              f"{r['gap_saltos_por_flit']:.4f} saltos/flit no perfil")
    print("\nEstabilidade: variação L1 da matriz / volume do perfil linear")
    for r in tabelas["estabilidade_perfil"]:
        caso = f"{r['programa']}/{r['nucleos']}"
        mapa = "igual" if r["mesmo_mapa"] else "diferente"
        print(f"{caso:17} {r['diferenca_trafego_pct']:6.2f}%  mapa {mapa}")
    print("\nIC t de Student com 3 pares; positivo indica redução.")
    print("O IC aleatório é condicional aos três mapas sorteados.")
    for nome in ("uniforme_ic95", "segundo_perfil_ic95"):
        if nome not in tabelas:
            continue
        print(f"\n{nome}: redução média e IC95% pareado (%)")
        for r in tabelas[nome]:
            caso = f"{r['programa']}/{r['nucleos']}"
            p = r.get("politica", "guloso v2")
            print(f"{caso:17} {p:10} {ROTULOS[r['metrica']]:10} "
                  f"{num(r['reducao_pct'])} "
                  f"[{num(r['ic95_inf_pct'])}, {num(r['ic95_sup_pct'])}]")
    if "segundo_perfil_ic95" not in tabelas:
        print("Sem CSV de reavaliação: estabilidade resume só os perfis.")
    if "perfil_com_matrizes" not in tabelas:
        print("φ do perfil, teto relaxado e E[D] requerem --matrizes.")
    else:
        print("\nPerfil com matrizes: φ, teto de redução e E[D] do aleatório")
        for r in tabelas["perfil_com_matrizes"]:
            caso = f"{r['programa']}/{r['nucleos']}"
            teto = num(r["teto_reducao_pct"])
            print(f"{caso:17} {r['phi_perfil']:.2%}  "
                  f"{teto}% ({r['tipo_teto']})  "
                  f"{r['d_aleatorio_esperado']:.4f} saltos/flit")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--campanha", type=Path, default=ROOT / "docs/projeto12/dados",
        help="pasta dos quatro CSVs originais ou saída de reproduzir.sh",
    )
    ap.add_argument("--saida", type=Path, help="grava apenas CSVs derivados")
    ap.add_argument(
        "--segundo-perfil", type=Path,
        help="CSV de avaliações do novo guloso, se estiver em outro caminho",
    )
    ap.add_argument(
        "--matrizes",
        type=Path,
        help="pasta opcional com perfil/ e mapas/ da mesma campanha para "
        "calcular φ, teto relaxado e esperança analítica do aleatório",
    )
    args = ap.parse_args()
    try:
        tabelas = confere_campanha(
            args.campanha, args.matrizes, args.segundo_perfil
        )
        mostra(tabelas)
        if args.saida is not None:
            for nome, linhas in tabelas.items():
                escreve_csv(args.saida / f"{nome}.csv", linhas)
    except ERROS_DADOS as erro:
        ap.exit(1, f"{erro}\n")


if __name__ == "__main__":
    main()
