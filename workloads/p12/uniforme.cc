// Copyright (c) 2026 The Project 12 contributors
// SPDX-License-Identifier: BSD-3-Clause

#include "comum.h"

namespace
{

using namespace p12;

class Uniforme
{
  public:
    explicit Uniforme(const Opcoes &op)
        : op(op), dados(size_t{op.threads} * op.linhas)
    {}

    uint64_t
    estadoInicial(unsigned t) const
    {
        return mistura(op.semente ^ t);
    }

    void
    escrita(unsigned t, unsigned it)
    {
        escreve(fatia(t), op, t, it);
    }

    uint64_t
    leitura(unsigned t, unsigned, uint64_t &estado)
    {
        return le(fatia(sorteia(t, estado)), op.linhas);
    }

    uint64_t
    esperado(unsigned t) const
    {
        auto estado = estadoInicial(t);
        uint64_t soma = 0;
        for (unsigned it = 0; it < op.iteracoes; ++it) {
            soma += somaEsperada(op, sorteia(t, estado), it);
        }
        return soma;
    }

  private:
    const Opcoes &op;
    std::vector<Linha> dados;

    Linha *
    fatia(unsigned t)
    {
        return dados.data() + size_t{t} * op.linhas;
    }

    unsigned
    sorteia(unsigned t, uint64_t &estado) const
    {
        unsigned outro;
        do {
            estado += UINT64_C(0x9e3779b97f4a7c15);
            // O numero de threads e uma potencia de dois (8 ou 16).
            outro = mistura(estado) & (op.threads - 1);
        } while (outro == t);
        return outro;
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
    Uniforme padrao(op);
    return p12::Execucao(op, padrao).roda();
}
