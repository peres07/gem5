# Workloads do Projeto 12

Os três executáveis X86 usam pthreads e recebem os mesmos argumentos:
`<threads> <iterações> <linhas de cache por mensagem> <semente>`.

- `vizinhanca`: cada thread escreve dois buffers e lê os buffers que seus
  vizinhos no anel escreveram para ela.
- `grupos`: os pares e os ímpares se comunicam em grupos separados. A fatia
  escrita por cada thread gira a cada iteração. `--blocos` usa dois grupos
  contíguos em vez de intercalados.
- `uniforme`: a cada iteração, cada thread lê a fatia de outro participante
  sorteado com probabilidade uniforme por seu gerador local.

### Compilar e testar

Na raiz do repositório, com compilador C++ e bibliotecas estáticas para X86:

```sh
make -C workloads/p12
make -C workloads/p12 check
```

`make` compila `libm5.a` com SCons se ela não existir e grava os executáveis
em `build/workloads/p12/`. O alvo `check` passa `--nativo` para testar no
host, sem executar as instruções m5 nem exigir que a CPU física de cada
thread seja igual ao seu índice lógico.

### Executar no gem5

Com `build/X86/gem5.opt` compilado da branch do projeto:

```sh
build/X86/gem5.opt -d m5out/p12-vizinhanca \
    configs/projetos/p12/sistema_p12.py \
    --num-cpus=8 --mesh-rows=2 --num-l2caches=8 --num-dirs=8 \
    --p12-matriz --cmd=build/workloads/p12/vizinhanca --options='8 10 4 11'
```

Sem `--nativo`, as instruções m5 delimitam a região de interesse. O primeiro
bloco do `stats.txt` contém essa região. O programa imprime `thread=... cpu=...
soma=...` para cada participante e `checksum=... esperado=...` no fim. Uma
soma local incorreta ou uma thread que não rodou na CPU esperada faz o
programa retornar um código de erro.

### Perfil, mapeamento e avaliação automatizados

Piloto para `grupos` na malha 2×4, com sementes distintas para o perfil e
para a avaliação:

```sh
python3 configs/projetos/p12/fluxo_p12.py grupos 8 --politica guloso
```

Para a campanha, calibre `--iteracoes` e `--linhas-mensagem` em um piloto
antes de rodar todas as simulações. Use os mesmos parâmetros nas duas
passadas. Exemplo com os valores curtos do piloto:

```sh
python3 configs/projetos/p12/campanha_p12.py --listar
python3 configs/projetos/p12/campanha_p12.py --fase perfis --jobs 2 \
    --iteracoes 10 --linhas-mensagem 4
python3 configs/projetos/p12/campanha_p12.py --fase avaliacoes --jobs 2 \
    --iteracoes 10 --linhas-mensagem 4 --estabilidade
```

Os resultados ficam em `m5out/p12/` por padrão. A campanha grava
`metricas.csv` com uma linha por avaliação e, com `--estabilidade`, um
`estabilidade.csv` com a comparação entre perfis linear e guloso para cada
caso. Repetir a campanha só executa novamente casos sem resultados válidos
ou com entradas diferentes. Use diretórios `--saida` distintos para rodar
campanhas independentes simultaneamente.

O extrator usa o primeiro bloco de `stats.txt` e converte as latências em
ticks para ciclos pelo relógio da rede em `config.ini`. Para comparar a
distância medida com `average_hops`, `--flits-transito` define o máximo
assumido de flits em trânsito em cada fronteira da ROI (padrão: 32). Esse
limite é registrado no CSV; não é uma medida de ocupação. Para exigir
concordância sem flits em trânsito, use `--flits-transito 0`.
