"""Carga Python com tres padroes de comunicacao em memoria compartilhada."""

import argparse
import ctypes
import random
import threading


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


def executar(args):
    n, fases, linhas = args.threads, args.fases, args.linhas_msg
    m5ops = ctypes.CDLL(args.m5ops) if args.m5ops else None
    libc = ctypes.CDLL(None, use_errno=True)
    if m5ops:
        for op in (m5ops.m5_reset_stats, m5ops.m5_dump_stats):
            op.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
            op.restype = None

    # Cada thread escreve em linhas de cache so dela.
    largura = linhas * 8
    bruto = ctypes.create_string_buffer(n * linhas * 64 + 63)
    inicio = -ctypes.addressof(bruto) % 64
    dados = (ctypes.c_uint64 * (n * largura)).from_buffer(bruto, inicio)

    leituras = []
    esperado = 0
    for t in range(n):
        sorteio = random.Random(args.semente * n + t)
        plano = [destinos(args.padrao, t, n, sorteio) for _ in range(fases)]
        leituras.append(plano)
        esperado += sum(
            (outro * fases + fase + 1) * linhas
            for fase, pares in enumerate(plano)
            for outro in pares
        )

    def abre_roi():
        if m5ops:
            m5ops.m5_reset_stats(0, 0)

    def fecha_roi():
        if m5ops:
            m5ops.m5_dump_stats(0, 0)

    inicio = threading.Barrier(n, action=abre_roi)
    troca = threading.Barrier(n)
    fim = threading.Barrier(n, action=fecha_roi)
    somas = [0] * n
    cpus = [None] * n

    def trabalho(t):
        if m5ops:
            # getcpu direto no Linux x86-64, sem o atalho da libc.
            cpu = ctypes.c_uint()
            if libc.syscall(309, ctypes.byref(cpu), None, None) == 0:
                cpus[t] = cpu.value
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

    threads = [threading.Thread(target=trabalho, args=(t,)) for t in range(1, n)]
    for thread in threads:
        thread.start()
    trabalho(0)
    for thread in threads:
        thread.join()

    for t, cpu in enumerate(cpus):
        print(f"thread={t} cpu={cpu} soma={somas[t]}")
    soma = sum(somas)
    print(f"checksum={soma} esperado={esperado}", flush=True)
    return soma == esperado and (not m5ops or cpus == list(range(n)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("padrao", choices=("vizinhanca", "dois_grupos", "uniforme"))
    ap.add_argument("fases", type=int)
    ap.add_argument("--threads", type=int, choices=(8, 16), default=16)
    ap.add_argument("--linhas-msg", type=int, default=1)
    ap.add_argument("--semente", type=int, default=11)
    ap.add_argument("--m5ops", help="Biblioteca de operacoes m5 no gem5")
    args = ap.parse_args()
    if args.fases < 1 or args.linhas_msg < 1:
        ap.error("fases e linhas-msg devem ser positivos")
    if not executar(args):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
