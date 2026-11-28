// Copyright (c) 2026 The Project 12 contributors
// SPDX-License-Identifier: BSD-3-Clause

#include "comum.h"

namespace
{

using namespace p12;

struct Buffers
{
    Linha *para_esq;
    Linha *para_dir;
};

class Vizinhanca
{
  public:
    explicit Vizinhanca(const Opcoes &op)
        : op(op), dados(size_t{2} * op.threads * op.linhas)
    {}

    uint64_t
    estadoInicial(unsigned) const
    {
        return 0;
    }

    void
    escrita(unsigned t, unsigned it)
    {
        const auto b = buffers(t);
        escreve(b.para_esq, op, t, it, 0);
        escreve(b.para_dir, op, t, it, 1);
    }

    uint64_t
    leitura(unsigned t, unsigned, uint64_t &)
    {
        return le(buffers(esquerda(t)).para_dir, op.linhas) +
               le(buffers(direita(t)).para_esq, op.linhas);
    }

    uint64_t
    esperado(unsigned t) const
    {
        uint64_t soma = 0;
        for (unsigned it = 0; it < op.iteracoes; ++it) {
            soma += somaEsperada(op, esquerda(t), it, 1);
            soma += somaEsperada(op, direita(t), it, 0);
        }
        return soma;
    }

  private:
    const Opcoes &op;
    std::vector<Linha> dados;

    unsigned
    esquerda(unsigned t) const
    {
        return (t + op.threads - 1) % op.threads;
    }

    unsigned
    direita(unsigned t) const
    {
        return (t + 1) % op.threads;
    }

    Buffers
    buffers(unsigned t)
    {
        auto *inicio = dados.data() + size_t{2} * t * op.linhas;
        return {inicio, inicio + op.linhas};
    }
};

} // anonymous namespace

int
main(int argc, char **argv)
{
    p12::Opcoes op{};
    if (!p12::leOpcoes(argc, argv, op)) {
        return EXIT_FAILURE;
    }
    Vizinhanca padrao(op);
    return p12::Execucao(op, padrao).roda();
}
