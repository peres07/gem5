# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Valida conservacao, destinos, saltos e linhas de base do Garnet."""

import argparse
import subprocess
from pathlib import Path

from extrai_p12 import (
    REDE,
    confere_conservacao,
    confere_saltos,
    estatistica,
)
from fluxo_p12 import ROOT
from matriz_p12 import (
    distancia,
    le_bloco,
    le_perfil,
)

LADO = 4
NOS = LADO**2
PACOTES = 16
DESTINO = 5


def destino(padrao, i):
    y, x = divmod(i, LADO)
    if padrao == "transpose":
        return x * LADO + y
    if padrao == "neighbor":
        return y * LADO + (x + 1) % LADO
    if padrao == "destino-unico":
        return DESTINO
    raise ValueError(f"padrao desconhecido: {padrao}")


def valida(pasta, padrao, vnet):
    stats = le_bloco(pasta)
    perfis = {u: le_perfil(pasta, u) for u in ("msgs", "flits")}
    totais = confere_conservacao(stats, perfis)
    l1 = [f"l1_cntrl{i}" for i in range(NOS)]
    dirs = [f"dir_cntrl{i}" for i in range(NOS)]
    pares = {(n, dirs[destino(padrao, i)]) for i, n in enumerate(l1)}
    posicoes = dict(zip(l1 + dirs, list(range(NOS)) * 2))
    largura = 5 if vnet == 2 else 1
    for unidade, fator in (("msgs", 1), ("flits", largura)):
        perfil = perfis[unidade]
        if perfil.nomes != l1 + dirs or perfil.roteador != posicoes:
            raise ValueError(f"{pasta}: IDs ou roteadores inesperados")
        nao_nulos = {
            (a, b): perfil.matriz[i][j]
            for i, a in enumerate(perfil.nomes)
            for j, b in enumerate(perfil.nomes)
            if perfil.matriz[i][j]
        }
        if nao_nulos != dict.fromkeys(pares, PACOTES * fator):
            raise ValueError(f"{pasta}: matriz {unidade} inesperada")
    custo = (
        PACOTES
        * largura
        * sum(distancia(posicoes[a], posicoes[b], LADO) for a, b in pares)
    )
    recebidos = estatistica(stats, f"{REDE}.flits_received::total")
    confere_saltos(
        totais["flits"],
        recebidos,
        custo,
        estatistica(stats, f"{REDE}.average_hops"),
        2 * (LADO - 1),
        0,
    )


def roda(gem5, pasta, padrao, vnet, coleta, topologia="Mesh_XY"):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "p12_nos.csv").unlink(missing_ok=True)
    cmd = [
        str(gem5.resolve()),
        "-d",
        str(pasta.resolve()),
        "configs/example/garnet_synth_traffic.py",
        "--network=garnet",
        f"--num-cpus={NOS}",
        f"--num-dirs={NOS}",
        f"--mesh-rows={LADO}",
        f"--topology={topologia}",
        "--routing-algorithm=1",
        f"--synthetic={padrao if padrao != 'destino-unico' else 'transpose'}",
        f"--inj-vnet={vnet}",
        f"--num-packets-max={PACOTES}",
        # O tester compara sim-cycles com curTick(); a 1 GHz sao 1000 ticks/ciclo.
        "--injectionrate=0.02",
        "--sim-cycles=10000000",
        "--sys-clock=1GHz",
        "--ruby-clock=1GHz",
    ]
    if padrao == "destino-unico":
        cmd.append(f"--single-dest-id={DESTINO}")
    if coleta:
        cmd.append("--p12-matriz")
    with (pasta / "simulador.log").open("w") as log:
        subprocess.run(
            cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True
        )


def compara(a, b, ignora_matriz=False):
    def filtradas(pasta):
        return {
            k: v
            for k, v in le_bloco(pasta).items()
            if not k.startswith("host")
            and not (ignora_matriz and k.startswith(f"{REDE}.p12_"))
        }

    antes, depois = filtradas(a), filtradas(b)
    diferentes = [
        k
        for k in sorted(antes.keys() | depois.keys())
        if antes.get(k) != depois.get(k)
    ]
    if diferentes:
        raise ValueError(f"{a} != {b}: {', '.join(diferentes[:10])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--gem5", type=Path, default=ROOT / "build/Garnet_standalone/gem5.opt"
    )
    ap.add_argument(
        "--original",
        type=Path,
        help="gem5 sem P12, da mesma revisao-base e configuracao",
    )
    ap.add_argument("--saida", type=Path, default=ROOT / "m5out/p12-sintetico")
    args = ap.parse_args()
    try:
        for padrao, vnet in (
            ("transpose", 0),
            ("transpose", 2),
            ("neighbor", 0),
            ("destino-unico", 0),
        ):
            pasta = args.saida / f"{padrao}-{vnet}"
            roda(args.gem5, pasta, padrao, vnet, True)
            valida(pasta, padrao, vnet)

        xy = args.saida / "transpose-0"
        mapeada = args.saida / "mapeada-sem-mapa"
        roda(args.gem5, mapeada, "transpose", 0, True, "MeshMapeada")
        valida(mapeada, "transpose", 0)
        compara(xy, mapeada)

        desligada = args.saida / "coleta-desligada"
        roda(args.gem5, desligada, "transpose", 0, False)
        if (desligada / "p12_nos.csv").exists() or any(
            k.startswith(f"{REDE}.p12_") for k in le_bloco(desligada)
        ):
            raise ValueError("coleta desligada produziu artefatos P12")
        compara(xy, desligada, ignora_matriz=True)
        if args.original:
            original = args.saida / "original"
            roda(args.original, original, "transpose", 0, False)
            compara(original, desligada)
        else:
            print("Comparacao com binario original omitida (--original).")
    except (OSError, ValueError, subprocess.CalledProcessError) as erro:
        ap.exit(1, f"Falha: {erro}; veja {args.saida}\n")
    print(f"Validacao sintetica OK: {args.saida}")


if __name__ == "__main__":
    main()
