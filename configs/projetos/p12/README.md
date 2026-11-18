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

Rode primeiro uma entrada curta com perfil linear e avaliação gulosa:

```sh
python3 configs/projetos/p12/fluxo_p12.py dois_grupos \
    --nucleos 8 --fases 3 \
    --m5ops util/m5/build/x86/out/libm5ops.so \
    --saida resultados/p12-teste
```

A campanha segue a Parte 1: 16 núcleos O3, um perfil por padrão e
21 avaliações (linear, gulosa e cinco sementes aleatórias por padrão).
Por padrão, usa 20.000 fases para vizinhança e dois grupos e 5.000 para
uniforme. Calibre com `--fases` em um diretório separado antes de
executar a campanha completa.

```sh
python3 configs/projetos/p12/campanha_p12.py \
    --m5ops util/m5/build/x86/out/libm5ops.so \
    --saida resultados/p12-campanha
```

Cada simulação preserva o comando, `config.ini`, `stats.txt`,
`simout.txt` e `p12_nos.csv`. O script só marca uma execução como
concluída após conferir o checksum, as CPUs, as contagens, a distância
e o mapa solicitado. Use um diretório novo se alterar a configuração
ou recompilar o simulador. A campanha escreve `metricas.csv`, com
tempo simulado, distâncias, saltos e latência. Ela também compara o
perfil linear com o tráfego da avaliação gulosa para verificar a
estabilidade do mapa.
