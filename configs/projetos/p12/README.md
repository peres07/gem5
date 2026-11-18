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
