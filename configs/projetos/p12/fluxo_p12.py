# SPDX-License-Identifier: BSD-3-Clause
"""Executa o perfil linear, gera o mapa e avalia uma politica."""

import argparse
import json
import shlex
import subprocess
from pathlib import Path

from extrai_p12 import extrai
from mapeador_p12 import POLITICAS
from matriz_p12 import d_ponderada, le_perfil

RAIZ = Path(__file__).resolve().parents[3]
PADROES = ("vizinhanca", "dois_grupos", "uniforme")


def argumentos():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gem5", type=Path, default=RAIZ / "build/X86/gem5.opt")
    ap.add_argument("--python", type=Path, default=Path("/usr/bin/python3"))
    ap.add_argument("--helper", type=Path, default=Path("/usr/bin/true"))
    ap.add_argument("--m5ops", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--nucleos", type=int, choices=(8, 16), default=16)
    ap.add_argument("--fases", type=int)
    ap.add_argument("--linhas-msg", type=int, default=1)
    ap.add_argument("--semente", type=int, default=11)
    return ap


def prepara(ap):
    args = ap.parse_args()
    for nome in ("gem5", "python", "helper", "m5ops", "saida"):
        caminho = getattr(args, nome).resolve()
        setattr(args, nome, caminho)
        if nome != "saida" and not caminho.is_file():
            ap.error(f"arquivo inexistente: {caminho}")
    if args.linhas_msg < 1 or (args.fases is not None and args.fases < 1):
        ap.error("fases e linhas-msg devem ser positivos")
    return args


def executa(args, pasta, padrao, fases, arquivo=None):
    carga = RAIZ / "workloads/p12/comunicacao.py"
    opcoes = shlex.join([
        "-B", "-S", str(carga), padrao, str(fases),
        "--threads", str(args.nucleos),
        "--linhas-msg", str(args.linhas_msg),
        "--semente", str(args.semente),
        "--m5ops", str(args.m5ops),
    ])
    cmd = [
        str(args.gem5), f"--outdir={pasta}", "--redirect-stdout",
        str(Path(__file__).with_name("sistema_p12.py")),
        "--network=garnet", "--topology=MeshMapeada",
        "--routing-algorithm=1", "--cpu-type=X86O3CPU",
        "--sys-clock=2GHz", "--ruby-clock=2GHz",
        f"--num-cpus={args.nucleos}", f"--mesh-rows={args.nucleos // 4}",
        f"--num-l2caches={args.nucleos}", f"--num-dirs={args.nucleos}",
        "--mem-size=4GiB", "--l1i_size=32KiB", "--l1d_size=32KiB",
        "--l1i_assoc=4", "--l1d_assoc=4", "--l2_size=512KiB", "--l2_assoc=8",
        f"--cmd={args.python}", f"--options={opcoes}",
        f"--p12-helper={args.helper}", "--p12-matriz",
    ]
    if arquivo:
        cmd.append(f"--p12-mapa={arquivo}")
    pasta.mkdir(parents=True, exist_ok=True)
    registro = pasta / "comando.json"
    if registro.exists() and json.loads(registro.read_text()) != cmd:
        raise ValueError(f"{pasta}: comando diferente; use outra saida")
    registro.write_text(json.dumps(cmd, indent=2) + "\n")
    concluido = pasta / ".concluido"
    if not concluido.exists():
        print(pasta, flush=True)
        subprocess.run(cmd, check=True, cwd=RAIZ)
    return concluido


def perfil(args, pasta, padrao, fases):
    concluido = executa(args, pasta, padrao, fases)
    valores = extrai(pasta, 4)
    concluido.touch()
    return le_perfil(pasta), valores


def mapeia(args, origem, dados, pasta, politica, semente_mapa):
    mapa = POLITICAS[politica](dados, args.nucleos // 4, 4, semente_mapa)
    previsto = d_ponderada(dados, mapa, 4)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{politica}-{semente_mapa}.json"
    arquivo.write_text(json.dumps({
        "mapa": mapa, "politica": politica, "semente": semente_mapa,
        "perfil": str(origem), "linhas": args.nucleos // 4, "colunas": 4,
        "unidade": "flits", "distancia_prevista": previsto,
    }, indent=2, sort_keys=True) + "\n")
    return arquivo, mapa, previsto


def avalia(args, pasta, padrao, fases, arquivo, mapa, previsto, referencia):
    concluido = executa(args, pasta, padrao, fases, arquivo)
    valores = extrai(pasta, 4, mapa, previsto)
    if valores["checksum"] != referencia["checksum"]:
        raise ValueError(f"{pasta}: checksum difere do perfil")
    concluido.touch()
    return valores


if __name__ == "__main__":
    ap = argumentos()
    ap.add_argument("padrao", choices=PADROES)
    ap.add_argument("--politica", choices=("linear", "guloso", "aleatorio"),
                    default="guloso")
    ap.add_argument("--semente-mapa", type=int, default=11)
    args = prepara(ap)
    fases = args.fases or 2
    origem = args.saida / "perfil"
    dados, referencia = perfil(args, origem, args.padrao, fases)
    arquivo, mapa, previsto = mapeia(
        args, origem, dados, args.saida / "mapas", args.politica,
        args.semente_mapa,
    )
    valores = avalia(
        args, args.saida / arquivo.stem, args.padrao, fases, arquivo, mapa,
        previsto, referencia,
    )
    print(json.dumps(valores, indent=2))
