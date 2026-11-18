# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Carga Python com tres padroes de comunicacao em memoria compartilhada."""

import sys
import threading
from array import array
from types import SimpleNamespace


def destinos(padrao, t, n, sorteio):
    if padrao == "vizinhanca":
        linha, coluna = divmod(t, 4)
        return [
            i for i in range(n)
            if abs(i // 4 - linha) + abs(i % 4 - coluna) == 1
        ]
    if padrao == "dois_grupos":
        return [i for i in range(n) if i != t and i % 2 == t % 2]
    outro = sorteio.randrange(n - 1)
    return [outro + (outro >= t)]


def carrega_m5ops(caminho):
    if not caminho:
        return None
    pasta, _, nome = caminho.rpartition("/")
    if nome != "_p12_m5.so":
        raise ValueError("use --m5ops com o arquivo _p12_m5.so")
    sys.path.insert(0, pasta or ".")
    try:
        return __import__("_p12_m5")
    finally:
        sys.path.pop(0)


def executar(args):
    n, fases, linhas = args.threads, args.fases, args.linhas_msg
    m5ops = carrega_m5ops(args.m5ops)

    # Alinha o inicio e separa os buffers em linhas de cache de 64 bytes.
    largura = linhas * 8
    bruto = array("Q", [0]) * (n * largura + 7)
    inicio_dados = (-bruto.buffer_info()[0] % 64) // bruto.itemsize
    dados = memoryview(bruto)[inicio_dados:inicio_dados + n * largura]

    if args.padrao == "uniforme":
        from random import Random
    leituras = []
    esperado = 0
    for t in range(n):
        sorteio = (
            Random(args.semente * n + t) if args.padrao == "uniforme" else None
        )
        plano = [destinos(args.padrao, t, n, sorteio) for _ in range(fases)]
        leituras.append(plano)
        esperado += sum(
            (outro * fases + fase + 1) * linhas
            for fase, pares in enumerate(plano)
            for outro in pares
        )

    def abre_roi():
        if m5ops:
            print("p12: inicio da regiao de interesse", flush=True)
            m5ops.abre_roi()

    def fecha_roi():
        if m5ops:
            m5ops.fecha_roi()
            print("p12: fim da regiao de interesse", flush=True)

    inicio = threading.Barrier(n, action=abre_roi)
    troca = threading.Barrier(n)
    fim = threading.Barrier(n, action=fecha_roi)
    somas = [0] * n
    cpus = [None] * n

    def calcula(t):
        if m5ops:
            try:
                cpus[t] = m5ops.cpu_atual()
            except OSError as erro:
                raise RuntimeError(f"getcpu falhou na thread {t}") from erro
            if cpus[t] != t:
                raise RuntimeError(f"thread {t} executou na CPU {cpus[t]}")
        inicio.wait()
        total = 0
        for fase, pares in enumerate(leituras[t]):
            for pos in range(t * largura, (t + 1) * largura, 8):
                dados[pos] = t * fases + fase + 1
            troca.wait()
            for outro in pares:
                for pos in range(outro * largura, (outro + 1) * largura, 8):
                    total += dados[pos]
            troca.wait()
        fim.wait()
        somas[t] = total

    erros = [None] * n

    def trabalho(t):
        try:
            calcula(t)
        except threading.BrokenBarrierError:
            return  # A falha da outra thread ja interrompeu a rodada.
        except Exception as erro:
            erros[t] = erro
            for barreira in (inicio, troca, fim):
                barreira.abort()

    if m5ops:
        if getattr(args, "aquecimento", 0):
            m5ops.prepara()
        print(f"p12: iniciando {n} threads para {args.padrao}", flush=True)
    threads = []
    try:
        for t in range(1, n):
            thread = threading.Thread(target=trabalho, args=(t,))
            thread.start()
            threads.append(thread)
        trabalho(0)
    except RuntimeError:
        for barreira in (inicio, troca, fim):
            barreira.abort()
        raise
    finally:
        for thread in threads:
            thread.join()
    for erro in erros:
        if erro is not None:
            raise RuntimeError(str(erro)) from erro

    for t, cpu in enumerate(cpus):
        print(f"thread={t} cpu={cpu} soma={somas[t]}")
    soma = sum(somas)
    print(f"checksum={soma} esperado={esperado}", flush=True)
    valido = soma == esperado and (not m5ops or cpus == list(range(n)))
    if m5ops and valido:
        m5ops.encerra()
    return valido


def main():
    uso = ("comunicacao.py PADRAO FASES [--threads N] [--linhas-msg N] "
           "[--semente N] [--m5ops CAMINHO] [--aquecimento 0|1]")
    if sys.argv[1:] in (["-h"], ["--help"]):
        print(uso)
        return
    args = SimpleNamespace(
        threads=16, linhas_msg=1, semente=11, m5ops=None, aquecimento=0,
    )
    try:
        padrao, fases, *opcoes = sys.argv[1:]
        args.padrao, args.fases = padrao, int(fases)
        campos = ("threads", "linhas_msg", "semente", "m5ops", "aquecimento")
        for opcao, valor in zip(opcoes[::2], opcoes[1::2], strict=True):
            campo = opcao.removeprefix("--").replace("-", "_")
            if not opcao.startswith("--") or campo not in campos:
                raise ValueError(f"opcao invalida: {opcao}")
            setattr(args, campo, valor if campo == "m5ops" else int(valor))
        if padrao not in ("vizinhanca", "dois_grupos", "uniforme"):
            raise ValueError(f"padrao invalido: {padrao}")
        if args.threads not in (8, 16):
            raise ValueError("threads deve ser 8 ou 16")
        if args.fases < 1 or args.linhas_msg < 1:
            raise ValueError("fases e linhas-msg devem ser positivos")
        if args.aquecimento not in (0, 1) or (
            args.aquecimento and not args.m5ops
        ):
            raise ValueError("aquecimento deve ser 0 ou 1 e requer m5ops")
        valido = executar(args)
    except (ImportError, OSError, RuntimeError, ValueError) as erro:
        print(f"{uso}\n{erro}", file=sys.stderr, flush=True)
        raise SystemExit(1) from erro
    if not valido:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
