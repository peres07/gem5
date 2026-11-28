# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Executa perfil, gera mapas e avalia um programa do Projeto 12."""

import argparse
import hashlib
import json
import shlex
import subprocess
from configparser import Error as IniError
from dataclasses import dataclass
from pathlib import Path

from extrai_p12 import (
    TRANSITO_PADRAO,
    escreve_csv,
    extrai,
)
from mapeador_p12 import (
    POLITICAS,
    cria_mapa,
)

ROOT = Path(__file__).resolve().parents[3]
SISTEMA = Path(__file__).with_name("sistema_p12.py").resolve()
PROGRAMAS = ("vizinhanca", "grupos", "uniforme")
MALHAS = {8: (2, 4), 16: (4, 4)}
SAIDAS = ("stats.txt", "p12_nos.csv", "config.ini", "simulador.log")
ERROS_DADOS = (OSError, ValueError, KeyError, TypeError, IniError)


def escreve_json(caminho, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, indent=2, sort_keys=True) + "\n"
    if caminho.exists() and caminho.read_text() == texto:
        return
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(texto)
    temporario.replace(caminho)


def digest(arquivo):
    return hashlib.sha256(arquivo.read_bytes()).hexdigest()


def identidade_executavel(arquivo):
    info = arquivo.stat()
    return [info.st_size, info.st_mtime_ns, info.st_ctime_ns]


@dataclass(frozen=True)
class Fluxo:
    saida: Path
    gem5: Path
    workloads: Path
    iteracoes: int
    linhas_mensagem: int
    limite: int = TRANSITO_PADRAO

    def roda(
        self,
        pasta,
        programa,
        nucleos,
        semente,
        mapa=None,
        executar=True,
        topologia="MeshMapeada",
    ):
        pasta = pasta.resolve()
        gem5 = self.gem5.resolve()
        binario = (self.workloads / programa).resolve()
        linhas, colunas = MALHAS[nucleos]
        cmd = [
            str(gem5),
            "-d",
            str(pasta),
            str(SISTEMA),
            "--cpu-type=X86TimingSimpleCPU",
            "--network=garnet",
            f"--topology={topologia}",
            "--routing-algorithm=1",
            "--router-latency=1",
            "--link-latency=1",
            "--vcs-per-vnet=4",
            f"--num-cpus={nucleos}",
            f"--num-dirs={nucleos}",
            f"--num-l2caches={nucleos}",
            f"--mesh-rows={linhas}",
            "--p12-matriz",
            f"--cmd={binario}",
            f"--options={nucleos} {self.iteracoes} "
            f"{self.linhas_mensagem} {semente}",
        ]
        if mapa is not None:
            mapa = mapa.resolve()
            cmd.append(f"--p12-mapa={mapa}")
        assinatura = {
            "comando": cmd,
            "gem5": identidade_executavel(gem5),
            "workload": identidade_executavel(binario),
            "sistema_sha256": digest(SISTEMA),
            "topologia_sha256": digest(
                ROOT / "configs/topologies/MeshMapeada.py"
            ),
            "mapa_sha256": digest(mapa) if mapa else None,
        }
        marco = pasta / "concluido.json"
        try:
            if json.loads(marco.read_text()) == assinatura:
                return extrai(pasta, linhas, colunas, mapa, self.limite)
        except ERROS_DADOS:
            pass
        if not executar:
            raise ValueError(
                f"perfil ausente, desatualizado ou invalido: {pasta}"
            )

        pasta.mkdir(parents=True, exist_ok=True)
        marco.unlink(missing_ok=True)
        for nome in SAIDAS:
            (pasta / nome).unlink(missing_ok=True)
        escreve_json(pasta / "execucao.json", assinatura)
        log = pasta / "simulador.log"
        with log.open("w") as arq:
            arq.write(shlex.join(cmd) + "\n")
            arq.flush()
            resultado = subprocess.run(
                cmd,
                cwd=ROOT,
                stdout=arq,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if resultado.returncode:
            raise ValueError(
                f"gem5 retornou {resultado.returncode}; veja {log}"
            )
        try:
            metricas = extrai(pasta, linhas, colunas, mapa, self.limite)
        except ERROS_DADOS as erro:
            raise ValueError(f"execucao invalida em {pasta}: {erro}") from erro
        escreve_json(marco, assinatura)
        return metricas

    def perfil(self, programa, nucleos, semente, executar=True):
        pasta = self.saida / "perfil" / f"{programa}-{nucleos}"
        self.roda(pasta, programa, nucleos, semente, executar=executar)
        return pasta

    def mapeia(self, dir_perfil, politica, semente, nucleos, unidade="flits"):
        linhas, colunas = MALHAS[nucleos]
        caminho = (
            self.saida
            / "mapas"
            / (f"{dir_perfil.name}-{politica}-{semente}-{unidade}.json")
        )
        mapa = cria_mapa(
            dir_perfil, politica, linhas, colunas, semente, unidade
        )
        mapa["perfil_sha256"] = self.assinatura_perfil(dir_perfil)
        escreve_json(caminho, mapa)
        return caminho

    @staticmethod
    def assinatura_perfil(dir_perfil):
        return (
            digest(dir_perfil / "stats.txt")
            + ":"
            + digest(dir_perfil / "p12_nos.csv")
        )

    def avalia(self, programa, nucleos, mapa, semente):
        pasta = self.saida / "avaliacao" / mapa.stem / f"perturb-{semente}"
        dados = json.loads(mapa.read_text())
        metricas = self.roda(pasta, programa, nucleos, semente, mapa)
        return {
            "programa": programa,
            "nucleos": nucleos,
            "linhas": dados["linhas"],
            "colunas": dados["colunas"],
            "politica": dados["politica"],
            "semente_mapa": dados["semente"],
            "semente_perturbacao": semente,
            "unidade_mapa": dados["unidade"],
            "execucao": str(pasta.resolve()),
            **metricas,
        }


def adiciona_opcoes(ap):
    ap.add_argument("--gem5", type=Path, default=ROOT / "build/X86/gem5.opt")
    ap.add_argument(
        "--workloads", type=Path, default=ROOT / "build/workloads/p12"
    )
    ap.add_argument("--saida", type=Path, default=ROOT / "m5out/p12")
    ap.add_argument("--iteracoes", type=int, default=10)
    ap.add_argument("--linhas-mensagem", type=int, default=4)
    ap.add_argument("--semente-perfil", type=int, default=1)
    ap.add_argument("--flits-transito", type=int, default=TRANSITO_PADRAO)


def configura(ap, args):
    if not 0 < args.iteracoes < 2**32 or not 0 < args.linhas_mensagem < 2**32:
        ap.error("iteracoes e linhas por mensagem devem ser uint32 positivos")
    if not 0 <= args.semente_perfil < 2**64 or args.flits_transito < 0:
        ap.error("semente deve ser uint64 e flits-transito nao negativo")
    return Fluxo(
        args.saida.resolve(),
        args.gem5.resolve(),
        args.workloads.resolve(),
        args.iteracoes,
        args.linhas_mensagem,
        args.flits_transito,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    adiciona_opcoes(ap)
    ap.add_argument("programa", choices=PROGRAMAS)
    ap.add_argument("nucleos", type=int, choices=MALHAS)
    ap.add_argument("--politica", choices=POLITICAS, default="guloso")
    ap.add_argument("--semente-mapa", type=int, default=1)
    ap.add_argument("--semente-perturbacao", type=int, default=11)
    ap.add_argument("--unidade", choices=("flits", "msgs"), default="flits")
    args = ap.parse_args()
    fluxo = configura(ap, args)
    if not 0 <= args.semente_perturbacao < 2**64:
        ap.error("semente de perturbacao deve ser uint64")
    if args.politica == "otimo" and args.nucleos != 8:
        ap.error("politica otimo permitida apenas para 8 nucleos")
    try:
        perfil = fluxo.perfil(args.programa, args.nucleos, args.semente_perfil)
        mapa = fluxo.mapeia(
            perfil,
            args.politica,
            args.semente_mapa,
            args.nucleos,
            args.unidade,
        )
        linha = fluxo.avalia(
            args.programa,
            args.nucleos,
            mapa,
            args.semente_perturbacao,
        )
        saida = Path(linha["execucao"]) / "metricas.csv"
        escreve_csv(saida, [linha])
    except ERROS_DADOS as erro:
        ap.exit(1, f"{erro}\n")
    print(saida)


if __name__ == "__main__":
    main()
