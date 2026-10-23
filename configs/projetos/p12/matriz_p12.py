"""Le a matriz de trafego do Garnet no bloco de interesse."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Perfil:
    nomes: list[str]
    matriz: list[list[int]]
    roteador: dict[str, int]


def le_perfil(diretorio, unidade="flits", bloco=0):
    if unidade not in ("flits", "msgs"):
        raise ValueError("unidade deve ser flits ou msgs")
    pasta = Path(diretorio)
    with (pasta / "p12_nos.csv").open(newline="") as arq:
        nos = sorted(csv.DictReader(arq), key=lambda x: int(x["ni"]))
    if [int(no["ni"]) for no in nos] != list(range(len(nos))):
        raise ValueError("identificadores locais invalidos no p12_nos.csv")
    nomes = [no["controlador"].rsplit(".", 1)[-1] for no in nos]
    if len(set(nomes)) != len(nomes):
        raise ValueError("nomes de controladores repetidos")
    roteador = {nome: int(no["roteador"]) for nome, no in zip(nomes, nos)}
    matriz = [[0] * len(nomes) for _ in nomes]
    indice = {nome: i for i, nome in enumerate(nomes)}
    padrao = re.compile(rf"^system\.ruby\.network\.p12_{unidade}_(\w+)::(\w+)$")

    texto = (pasta / "stats.txt").read_text()
    blocos = re.findall(
        r"---------- Begin Simulation Statistics ----------(.*?)"
        r"---------- End Simulation Statistics\s*----------",
        texto,
        re.S,
    )
    if bloco >= len(blocos) or bloco < 0:
        raise ValueError("bloco de estatisticas nao encontrado")
    for linha in blocos[bloco].splitlines():
        partes = linha.split()
        if len(partes) < 2:
            continue
        achou = padrao.fullmatch(partes[0])
        if achou:
            origem, destino = achou.groups()
            if origem not in indice or destino not in indice:
                raise ValueError(f"controlador desconhecido: {origem}, {destino}")
            matriz[indice[origem]][indice[destino]] += int(partes[1])
    return Perfil(nomes, matriz, roteador)


def distancia(r1, r2, colunas):
    return abs(r1 // colunas - r2 // colunas) + abs(r1 % colunas - r2 % colunas)


def d_ponderada(perfil, mapa, colunas):
    total = sum(map(sum, perfil.matriz))
    if total == 0:
        raise ValueError("matriz de trafego vazia")
    custo = sum(
        peso * distancia(mapa[perfil.nomes[i]], mapa[perfil.nomes[j]], colunas)
        for i, linha in enumerate(perfil.matriz)
        for j, peso in enumerate(linha)
    )
    return custo / total


def fracao_l1_l1(perfil):
    total = sum(map(sum, perfil.matriz))
    if total == 0:
        raise ValueError("matriz de trafego vazia")
    movel = [i for i, n in enumerate(perfil.nomes) if n.startswith("l1_cntrl")]
    return sum(perfil.matriz[i][j] for i in movel for j in movel) / total
