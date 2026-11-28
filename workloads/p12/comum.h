// Copyright (c) 2026 The Project 12 contributors
// SPDX-License-Identifier: BSD-3-Clause

#ifndef WORKLOADS_P12_COMUM_H
#define WORKLOADS_P12_COMUM_H

#include <pthread.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <charconv>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string_view>
#include <system_error>
#include <vector>

#include "gem5/m5ops.h"

namespace p12
{

struct alignas(64) Linha
{
    uint64_t v[8];
};
static_assert(sizeof(Linha) == 64);

struct Opcoes
{
    unsigned threads, iteracoes, linhas;
    uint64_t semente;
    bool nativo = false;
    bool blocos = false;
};

template <typename T>
bool
leInteiro(std::string_view texto, T &valor)
{
    const auto fim = texto.data() + texto.size();
    const auto resultado = std::from_chars(texto.data(), fim, valor);
    return resultado.ec == std::errc{} && resultado.ptr == fim;
}

inline bool
leOpcoes(int argc, char **argv, Opcoes &op, bool aceita_blocos = false)
{
    if (argc >= 5 && leInteiro(argv[1], op.threads) &&
        (op.threads == 8 || op.threads == 16) &&
        leInteiro(argv[2], op.iteracoes) && op.iteracoes > 0 &&
        leInteiro(argv[3], op.linhas) && op.linhas > 0 &&
        leInteiro(argv[4], op.semente)) {
        int i = 5;
        for (; i < argc; ++i) {
            const std::string_view arg = argv[i];
            if (arg == "--nativo" && !op.nativo) {
                op.nativo = true;
            } else if (arg == "--blocos" && aceita_blocos && !op.blocos) {
                op.blocos = true;
            } else {
                break;
            }
        }
        if (i == argc) {
            return true;
        }
    }
    std::fprintf(
        stderr, "Uso: %s <8|16> <iteracoes> <linhas> <semente> [--nativo]%s\n",
        argv[0], aceita_blocos ? " [--blocos]" : "");
    return false;
}

inline void
conferePthread(int codigo, const char *operacao)
{
    if (codigo != 0) {
        std::fprintf(stderr, "%s falhou: %d\n", operacao, codigo);
        std::exit(EXIT_FAILURE);
    }
}

// SplitMix64: o estado e local a cada thread, sem compartilhar o RNG.
inline uint64_t
mistura(uint64_t valor)
{
    valor = (valor ^ (valor >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
    valor = (valor ^ (valor >> 27)) * UINT64_C(0x94d049bb133111eb);
    return valor ^ (valor >> 31);
}

inline void
perturba(uint64_t semente, unsigned t, unsigned it)
{
    auto passos = mistura((semente ^ (uint64_t{it} << 32)) + t) & 31;
    // Pequeno atraso em registradores, sem adicionar acessos aos buffers.
    while (passos--) {
        asm volatile("" : : "r"(passos));
    }
}

inline uint64_t
valorLinha(uint64_t semente, unsigned t, unsigned it, unsigned linha,
           unsigned canal)
{
    return mistura(semente ^ (uint64_t{t} << 48) ^ (uint64_t{canal} << 56) ^
                   (uint64_t{it} * UINT64_C(0x9e3779b97f4a7c15)) ^ linha);
}

inline void
escreve(Linha *buffer, const Opcoes &op, unsigned t, unsigned it,
        unsigned canal = 0)
{
    for (unsigned l = 0; l < op.linhas; ++l) {
        const auto valor = valorLinha(op.semente, t, it, l, canal);
        for (unsigned p = 0; p < 8; ++p) {
            buffer[l].v[p] = valor + p;
        }
    }
}

inline uint64_t
le(const Linha *buffer, unsigned linhas)
{
    uint64_t soma = 0;
    for (unsigned l = 0; l < linhas; ++l) {
        for (auto palavra : buffer[l].v) {
            soma += palavra;
        }
    }
    return soma;
}

// Referencia serial: calcula a soma sem ler os buffers compartilhados.
inline uint64_t
somaEsperada(const Opcoes &op, unsigned t, unsigned it, unsigned canal = 0)
{
    uint64_t soma = 0;
    for (unsigned l = 0; l < op.linhas; ++l) {
        soma += 8 * valorLinha(op.semente, t, it, l, canal) + 28;
    }
    return soma;
}

template <typename Padrao> class Execucao
{
  public:
    Execucao(const Opcoes &op, Padrao &padrao)
        : op(op), padrao(padrao), contextos(op.threads)
    {
        conferePthread(pthread_barrier_init(&barreira, nullptr, op.threads),
                       "pthread_barrier_init");
    }

    int
    roda()
    {
        std::vector<pthread_t> workers(op.threads - 1);
        for (unsigned t = 0; t < op.threads; ++t) {
            contextos[t].execucao = this;
            contextos[t].t = t;
        }
        for (unsigned t = 1; t < op.threads; ++t) {
            conferePthread(pthread_create(&workers[t - 1], nullptr,
                                          trabalhador, &contextos[t]),
                           "pthread_create");
        }
        trabalhador(&contextos[0]);
        for (auto thread : workers) {
            conferePthread(pthread_join(thread, nullptr), "pthread_join");
        }
        conferePthread(pthread_barrier_destroy(&barreira),
                       "pthread_barrier_destroy");

        bool correto = true;
        uint64_t soma = 0, esperado = 0;
        for (const auto &ctx : contextos) {
            const auto referencia = padrao.esperado(ctx.t);
            std::printf("thread=%u cpu=%d soma=%llu\n", ctx.t, ctx.cpu,
                        static_cast<unsigned long long>(ctx.soma));
            soma += ctx.soma;
            esperado += referencia;
            correto &= ctx.soma == referencia && ctx.cpu >= 0 &&
                       (op.nativo || ctx.cpu == static_cast<int>(ctx.t));
        }
        std::printf("checksum=%llu esperado=%llu\n",
                    static_cast<unsigned long long>(soma),
                    static_cast<unsigned long long>(esperado));
        return correto ? EXIT_SUCCESS : EXIT_FAILURE;
    }

  private:
    // Resultados e argumentos de threads distintas nao dividem uma linha.
    struct alignas(64) Contexto
    {
        Execucao *execucao;
        unsigned t;
        int cpu;
        uint64_t soma;
    };

    const Opcoes &op;
    Padrao &padrao;
    pthread_barrier_t barreira;
    std::vector<Contexto> contextos;

    void
    barreiraEspera()
    {
        const int codigo = pthread_barrier_wait(&barreira);
        if (codigo != PTHREAD_BARRIER_SERIAL_THREAD) {
            conferePthread(codigo, "pthread_barrier_wait");
        }
    }

    static void *
    trabalhador(void *arg)
    {
        auto &ctx = *static_cast<Contexto *>(arg);
        auto &exec = *ctx.execucao;
        const auto &op = exec.op;
        const unsigned t = ctx.t;
        unsigned cpu = 0;
        // Em SE X86 com uma thread de hardware por CPU, getcpu devolve
        // o ID do contexto, que corresponde ao ID da CPU.
        const auto codigo = syscall(SYS_getcpu, &cpu, nullptr, nullptr);
        ctx.cpu = codigo == 0 ? static_cast<int>(cpu) : -1;
        auto estado = exec.padrao.estadoInicial(t);

        exec.barreiraEspera();
        if (t == 0 && !op.nativo) {
            m5_reset_stats(0, 0);
        }
        exec.barreiraEspera();

        uint64_t total = 0;
        for (unsigned it = 0; it < op.iteracoes; ++it) {
            perturba(op.semente, t, it);
            exec.padrao.escrita(t, it);
            exec.barreiraEspera();
            total += exec.padrao.leitura(t, it, estado);
            exec.barreiraEspera();
        }

        if (t == 0 && !op.nativo) {
            m5_dump_stats(0, 0);
        }
        exec.barreiraEspera();
        ctx.soma = total;
        return nullptr;
    }
};

} // namespace p12

#endif // WORKLOADS_P12_COMUM_H
