# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Confere a campanha com execuções nativas das mesmas cargas."""

import argparse
import csv
from itertools import product
from pathlib import Path
import re
import subprocess

from campanha_p12 import PERTURBACOES
from fluxo_p12 import MALHAS, PROGRAMAS


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--workloads", type=Path, required=True)
    ap.add_argument("--iteracoes", type=int, required=True)
    ap.add_argument("--linhas-mensagem", type=int, required=True)
    ap.add_argument("--semente-perfil", type=int, required=True)
    args = ap.parse_args()

    sementes = sorted({args.semente_perfil, *PERTURBACOES})
    referencias = {}
    for programa, nucleos, semente in product(PROGRAMAS, MALHAS, sementes):
        comando = [
            str((args.workloads / programa).resolve()),
            str(nucleos),
            str(args.iteracoes),
            str(args.linhas_mensagem),
            str(semente),
            "--nativo",
        ]
        texto = subprocess.check_output(comando, text=True)
        resultado = re.findall(r"^checksum=(\d+) esperado=(\d+)$", texto, re.M)
        if len(resultado) != 1 or resultado[0][0] != resultado[0][1]:
            ap.exit(1, f"Checksum inválido na execução nativa: {comando}\n")
        referencias[programa, nucleos, semente] = int(resultado[0][0])

    for arquivo, esperado in (("metricas.csv", 99), ("segundo-perfil.csv", 18)):
        caminho = args.saida / arquivo
        with caminho.open(newline="") as dados:
            casos = list(csv.DictReader(dados))
        if len(casos) != esperado:
            ap.exit(1, f"{len(casos)} avaliações em {caminho}, esperadas {esperado}\n")
        for caso in casos:
            chave = (
                caso["programa"],
                int(caso["nucleos"]),
                int(caso["semente_perturbacao"]),
            )
            if referencias.get(chave) != int(caso["checksum"]):
                ap.exit(1, f"Checksum divergiu da referência: {caso['execucao']}\n")
        print(f"{arquivo}: {len(casos)} avaliações conferidas com as cargas nativas.")

    with (args.saida / "checksums-nativos.csv").open("w", newline="") as dados:
        gravador = csv.writer(dados)
        gravador.writerow(("programa", "nucleos", "semente", "checksum"))
        gravador.writerows((*chave, valor) for chave, valor in referencias.items())


if __name__ == "__main__":
    main()
