"""Padroes de comunicacao entre threads para o Projeto 12."""

import argparse
import ctypes
import threading


def destinos(padrao, t, n):
    if padrao == "vizinhanca":
        colunas = 4
        linha, coluna = divmod(t, colunas)
        vizinhos = []
        if linha > 0:
            vizinhos.append(t - colunas)
        if linha < n // colunas - 1:
            vizinhos.append(t + colunas)
        if coluna > 0:
            vizinhos.append(t - 1)
        if coluna < colunas - 1:
            vizinhos.append(t + 1)
        return vizinhos
    if padrao == "dois_grupos":
        return [i for i in range(n) if i != t and i % 2 == t % 2]
    return [i for i in range(n) if i != t]


def executar(padrao, fases, n, no_gem5):
    dados = (ctypes.c_uint64 * (n * 8))()
    somas = [0] * n
    barreira = threading.Barrier(n)
    getcpu = ctypes.CDLL(None).sched_getcpu
    getcpu.restype = ctypes.c_int

    def trabalho(id):
        t = getcpu() if no_gem5 else id
        if not 0 <= t < n:
            raise ValueError(f"thread fora dos nucleos: {t}")
        total = 0
        barreira.wait()
        for fase in range(fases):
            dados[t * 8] = t * 100000 + fase
            barreira.wait()
            for outro in destinos(padrao, t, n):
                total += dados[outro * 8]
            barreira.wait()
        somas[t] = total
        print(f"thread={t} cpu={getcpu()} soma={total}", flush=True)
        barreira.wait()

    threads = [threading.Thread(target=trabalho, args=(i,)) for i in range(1, n)]
    for thread in threads:
        thread.start()
    trabalho(0)
    for thread in threads:
        thread.join()

    soma = sum(somas)
    esperado = sum(
        outro * 100000 + fase
        for fase in range(fases)
        for t in range(n)
        for outro in destinos(padrao, t, n)
    )
    print(f"checksum={soma} esperado={esperado}", flush=True)
    return soma == esperado


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("padrao", choices=("vizinhanca", "dois_grupos", "uniforme"))
    ap.add_argument("fases", type=int)
    ap.add_argument("--threads", type=int, choices=(8, 16), default=16)
    ap.add_argument("--gem5", action="store_true")
    args = ap.parse_args()
    if args.fases < 1:
        ap.error("fases precisa ser positivo")
    if not executar(args.padrao, args.fases, args.threads, args.gem5):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
