# Projeto 12 — avaliação dos mapas

Use o gem5 X86 compilado com o protocolo MESI_Two_Level. A aplicação
simulada é `workloads/p12/comunicacao.py`, executada pelo Python do
Linux dentro do gem5. O Python também executa os scripts de avaliação
fora do simulador.
O interpretador simulado usa `-S` para evitar a inicialização de
pacotes de usuário e chamadas do sistema que o modo SE não oferece.

Na raiz do repositório, prepare a biblioteca usada pelo Python simulado
para marcar a região de interesse:

```sh
mkdir -p util/m5/build/x86/out
gcc -shared -fPIC -Wl,-z,noexecstack -I include \
    util/m5/src/abi/x86/m5op.S -o util/m5/build/x86/out/libm5ops.so
```

O argumento `--m5ops` seleciona a carga Python com CPU O3.
Para testar um perfil linear e uma avaliação gulosa na malha 2×4:

```sh
python3 configs/projetos/p12/fluxo_p12.py grupos 8 \
    --iteracoes 3 --politica guloso \
    --m5ops util/m5/build/x86/out/libm5ops.so \
    --saida resultados/p12-python-teste
```

A campanha em Python segue a Parte 1: 16 núcleos O3, um perfil por
padrão e 21 avaliações (linear, gulosa e cinco sementes aleatórias
por padrão). A semente da carga é a mesma para todas as políticas de
cada padrão. Por padrão, usa 20.000 fases para vizinhança e dois grupos
e 5.000 para uniforme. Calibre com `--iteracoes` em um diretório separado.

```sh
python3 configs/projetos/p12/campanha_p12.py \
    --m5ops util/m5/build/x86/out/libm5ops.so \
    --saida resultados/p12-python --estabilidade
```

Cada execução preserva o comando, `config.ini`, `stats.txt`,
`simulador.log` e `p12_nos.csv`. O fluxo valida o checksum, as CPUs,
a conservação do tráfego, os saltos e o mapa aplicado. A campanha
grava `metricas.csv` e, com `--estabilidade`, `estabilidade.csv`.

O modo C++ usa os mesmos scripts sem `--m5ops`. Consulte
[workloads/p12/README.md](../../../workloads/p12/README.md).

Na campanha Python, as barras de erro mostram o menor e o maior tempo
entre os cinco mapas aleatórios. No modo C++, mostram o intervalo de
confiança pareado das sementes de perturbação. Para gerar os quatro PNGs
a partir do CSV, instale o matplotlib no Python do host e execute:

```sh
python3 configs/projetos/p12/analisa_p12.py \
    resultados/p12-python/metricas.csv --saida resultados/p12-python/graficos
```

## Comparação com o gem5 original (G6)

A opção de coleta controla as matrizes P12 e o CSV dos controladores.
A revisão do projeto também mudou a leitura funcional do Ruby para
permitir a leitura dos dados em trânsito durante a criação de threads
em modo SE. Em X86 SE, a resposta ENOSYS para memfd_create permite\nque a libffi tente a alternativa de arquivo temporário. Essas\nadaptações são independentes da coleta. Compare o binário
modificado com um binário compilado da mesma revisão-base, usando as
mesmas opções de build e arquitetura:

```sh
python3 configs/projetos/p12/valida_sintetico_p12.py \
    --original /caminho/base/Garnet_standalone/gem5.opt
python3 configs/projetos/p12/valida_x86_p12.py \
    --original /caminho/base/X86/gem5.opt
```

O teste X86 usa as cargas C++ por padrão. Para testar Python com O3,
acrescente `--m5ops` e use um diretório de saída separado. Se a base
falhar na criação de threads, guarde o log e registre o resultado como
diferença de compatibilidade. A validação sintética não cobre esse caso.
