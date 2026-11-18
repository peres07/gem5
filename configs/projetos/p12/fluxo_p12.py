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
    confere_log,
    escreve_csv,
    extrai,
)
from mapeador_p12 import (
    POLITICAS,
    cria_mapa,
)
from matriz_p12 import le_bloco

ROOT = Path(__file__).resolve().parents[3]
CARGA_PYTHON = ROOT / "workloads/p12/comunicacao.py"
FASES_PYTHON = {"vizinhanca": 20000, "grupos": 20000, "uniforme": 5000}
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
    iteracoes: int | None
    linhas_mensagem: int
    limite: int = TRANSITO_PADRAO
    m5ops: Path | None = None
    python: Path = Path("/usr/bin/python3")
    helper: Path = Path("/usr/bin/true")

    def roda(
        self,
        pasta,
        programa,
        nucleos,
        semente,
        mapa=None,
        executar=True,
        topologia="MeshMapeada",
        coleta=True,
    ):
        pasta = pasta.resolve()
        gem5 = self.gem5.resolve()
        binario = (self.workloads / programa).resolve()
        cpu = "X86TimingSimpleCPU"
        opcoes = f"{nucleos} {self.iteracoes} {self.linhas_mensagem} {semente}"
        extra = []
        if self.m5ops is not None:
            binario = self.python.resolve()
            cpu = "X86O3CPU"
            padrao = "dois_grupos" if programa == "grupos" else programa
            fases = self.iteracoes or FASES_PYTHON[programa]
            opcoes = shlex.join([
                "-B", "-S", str(CARGA_PYTHON), padrao, str(fases),
                "--threads", str(nucleos),
                "--linhas-msg", str(self.linhas_mensagem),
                "--semente", str(semente),
                "--m5ops", str(self.m5ops),
            ])
            extra = [
                f"--p12-helper={self.helper.resolve()}",
                "--sys-clock=2GHz", "--ruby-clock=2GHz",
                "--mem-size=4GiB", "--mem-type=DDR3_1600_8x8",
                "--l1i_size=32KiB", "--l1d_size=32KiB",
                "--l1i_assoc=4", "--l1d_assoc=4",
                "--l2_size=512KiB", "--l2_assoc=8",
            ]
        linhas, colunas = MALHAS[nucleos]
        cmd = [
            str(gem5),
            "-d",
            str(pasta),
            str(SISTEMA),
            f"--cpu-type={cpu}",
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
            f"--cmd={binario}",
            f"--options={opcoes}",
            *extra,
        ]
        if coleta:
            cmd.append("--p12-matriz")
        elif mapa is not None:
            raise ValueError("a comparacao sem coleta usa apenas o mapa linear")
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
        if self.m5ops is not None:
            assinatura["carga_python"] = digest(CARGA_PYTHON)
            assinatura["m5ops"] = digest(self.m5ops)
            assinatura["helper"] = identidade_executavel(self.helper.resolve())
        def confere_saida():
            if coleta:
                return extrai(pasta, linhas, colunas, mapa, self.limite)
            stats = le_bloco(pasta)
            le_bloco(pasta, 1)
            if (pasta / "p12_nos.csv").exists() or any(
                k.startswith("system.ruby.network.p12_") for k in stats
            ):
                raise ValueError("coleta desligada produziu artefatos P12")
            return {"checksum": confere_log(pasta, nucleos)}

        marco = pasta / "concluido.json"
        try:
            if json.loads(marco.read_text()) == assinatura:
                return confere_saida()
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
            metricas = confere_saida()
        except ERROS_DADOS as erro:
            raise ValueError(f"execucao invalida em {pasta}: {erro}") from erro
        escreve_json(marco, assinatura)
        return metricas

    def perfil(self, programa, nucleos, semente, executar=True):
        pasta = self.saida / "perfil" / f"{programa}-{nucleos}"
        self.roda(pasta, programa, nucleos, semente, executar=executar)
        return pasta

    def caminho_mapa(self, dir_perfil, politica, semente, unidade):
        nome = f"{dir_perfil.name}-{politica}-{semente}-{unidade}.json"
        return self.saida / "mapas" / nome

    def mapeia(self, dir_perfil, politica, semente, nucleos, unidade="flits"):
        linhas, colunas = MALHAS[nucleos]
        caminho = self.caminho_mapa(dir_perfil, politica, semente, unidade)
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

    def avalia(self, programa, nucleos, mapa, semente, confere_perfil=False):
        pasta = self.saida / "avaliacao" / mapa.stem / f"perturb-{semente}"
        dados = json.loads(mapa.read_text())
        metricas = self.roda(pasta, programa, nucleos, semente, mapa)
        if confere_perfil:
            esperado = confere_log(Path(dados["perfil"]), nucleos)
            if metricas["checksum"] != esperado:
                raise ValueError(f"{pasta}: checksum difere do perfil")
        return {
            "programa": programa,
            "carga": "python" if self.m5ops else "cpp",
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
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--iteracoes", type=int)
    ap.add_argument("--linhas-mensagem", type=int)
    ap.add_argument("--m5ops", type=Path, help="usa a carga Python com CPU O3")
    ap.add_argument("--python", type=Path, default=Path("/usr/bin/python3"))
    ap.add_argument("--helper", type=Path, default=Path("/usr/bin/true"))
    ap.add_argument("--semente-perfil", type=int, default=1)
    ap.add_argument("--flits-transito", type=int, default=TRANSITO_PADRAO)


def configura(ap, args):
    if any(
        v is not None and not 0 < v < 2**32
        for v in (args.iteracoes, args.linhas_mensagem)
    ):
        ap.error("iteracoes e linhas por mensagem devem ser uint32 positivos")
    if not 0 <= args.semente_perfil < 2**64 or args.flits_transito < 0:
        ap.error("semente deve ser uint64 e flits-transito nao negativo")
    pasta_padrao = "m5out/p12-python" if args.m5ops else "m5out/p12"
    saida = args.saida or ROOT / pasta_padrao
    return Fluxo(
        saida.resolve(),
        args.gem5.resolve(),
        args.workloads.resolve(),
        args.iteracoes if args.m5ops else (args.iteracoes or 10),
        args.linhas_mensagem or (1 if args.m5ops else 4),
        args.flits_transito,
        args.m5ops.resolve() if args.m5ops else None,
        args.python.resolve(),
        args.helper.resolve(),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    adiciona_opcoes(ap)
    ap.add_argument("programa", choices=PROGRAMAS)
    ap.add_argument("nucleos", type=int, choices=MALHAS)
    ap.add_argument("--politica", choices=POLITICAS, default="guloso")
    ap.add_argument("--semente-mapa", type=int, default=1)
    ap.add_argument("--semente-perturbacao", type=int)
    ap.add_argument("--unidade", choices=("flits", "msgs"), default="flits")
    args = ap.parse_args()
    fluxo = configura(ap, args)
    semente = args.semente_perturbacao
    if semente is None:
        semente = args.semente_perfil if args.m5ops else 11
    if not 0 <= semente < 2**64:
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
            semente,
            confere_perfil=bool(args.m5ops and semente == args.semente_perfil),
        )
        saida = Path(linha["execucao"]) / "metricas.csv"
        escreve_csv(saida, [linha])
    except ERROS_DADOS as erro:
        ap.exit(1, f"{erro}\n")
    print(saida)


if __name__ == "__main__":
    main()
