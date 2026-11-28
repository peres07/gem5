// Copyright (c) 2026 The Project 12 contributors
// SPDX-License-Identifier: BSD-3-Clause

#include "comum.h"

namespace
{

using namespace p12;

class Grupos
{
  public:
    explicit Grupos(const Opcoes &op)
        : op(op),
          membros(op.threads / 2),
          dados(size_t{op.threads} * op.linhas)
    {}

    uint64_t
    estadoInicial(unsigned) const
    {
        return 0;
    }

    void
    escrita(unsigned t, unsigned it)
    {
        const unsigned segmento = (posicao(t) + it % membros) % membros;
        escreve(fatia(grupo(t), segmento), op, t, it);
    }

    uint64_t
    leitura(unsigned t, unsigned, uint64_t &)
    {
        uint64_t soma = 0;
        for (unsigned i = 0; i < membros; ++i) {
            soma += le(fatia(grupo(t), i), op.linhas);
        }
        return soma;
    }

    uint64_t
    esperado(unsigned t) const
    {
        uint64_t soma = 0;
        for (unsigned it = 0; it < op.iteracoes; ++it) {
            // Cada membro escreveu exatamente uma fatia, em qualquer ordem.
            for (unsigned outro = 0; outro < op.threads; ++outro) {
                if (grupo(outro) == grupo(t)) {
                    soma += somaEsperada(op, outro, it);
                }
            }
        }
        return soma;
    }

  private:
    const Opcoes &op;
    const unsigned membros;
    std::vector<Linha> dados;

    unsigned
    grupo(unsigned t) const
    {
        return op.blocos ? t / membros : t % 2;
    }

    unsigned
    posicao(unsigned t) const
    {
        return op.blocos ? t % membros : t / 2;
    }

    Linha *
    fatia(unsigned g, unsigned i)
    {
        return dados.data() + (size_t{g} * membros + i) * op.linhas;
    }
};

} // anonymous namespace

int
main(int argc, char **argv)
{
    p12::Opcoes op{};
    if (!p12::leOpcoes(argc, argv, op, true)) {
        return EXIT_FAILURE;
    }
    Grupos padrao(op);
    return p12::Execucao(op, padrao).roda();
}
