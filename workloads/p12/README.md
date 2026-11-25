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

Recompile o gem5 da branch do projeto: um executável anterior ao Projeto 12
não reconhece `p12_matriz`. O capítulo usa a versão `v25.1.0.0` como
referência; a branch atual está baseada no gem5 26.0.0.0.

```sh
scons build/X86/gem5.opt -j2
scons build/Garnet_standalone/gem5.opt -j2
```

Teste em X86:

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

### Validar o Garnet e gerar gráficos

```sh
python3 -m pytest -q configs/projetos/p12
python3 configs/projetos/p12/valida_sintetico_p12.py
python3 configs/projetos/p12/valida_x86_p12.py
python3 configs/projetos/p12/analisa_p12.py m5out/p12/metricas.csv \
    --saida m5out/p12/graficos
```

O validador sintético verifica conservação, posições não nulas e saltos
com a rede drenada. Compara também `Mesh_XY` com `MeshMapeada` sem mapa e
a coleta ligada com a desligada, excluindo métricas do host (por exemplo,
tempo de parede). Para testar G6 contra um simulador sem a instrumentação,
passe `--original /caminho/gem5.opt`, compilado na mesma revisão-base e com
a mesma configuração. Os gráficos requerem `matplotlib`; o intervalo de
confiança de 95% usa os três tempos normalizados pelo linear da mesma
semente. Para o aleatório, os três mapas são agregados dentro de cada
semente de perturbação, não tratados como nove observações independentes.
O validador X86 compara as topologias com os três workloads na malha 4×4 e
confere a reprodução do perfil via JSON linear e a troca das L1 0 e 5.
O arquivo `referencias.csv` da campanha compara os custos previstos,
incluindo a serpentina e o ciclo hamiltoniano para `vizinhanca` na 4×4,
e registra se a escolha gulosa muda ao usar mensagens no lugar de flits.

### Algoritmo e referências do capítulo

O CSV `p12_nos.csv` registra `ni,controlador,roteador`. O JSON do mapeador
contém o objeto `mapa` (todos os controladores, inclusive os fixos), as
dimensões da malha, caminho do perfil, unidade, política, semente e distância
prevista. Só as L1 se movem; as posições fixas são as do perfil linear.

`guloso` executa a construção e os desempates da §21.2.4, sem rever escolhas.
Há uma divergência no PDF: com os desempates centrais especificados, o
primeiro grupo da figura 21.2 ocupa `1, 2, 5, 6` e deixa o outro nas bordas.
Isso dá distância média `2`, não `16/12`. O segundo valor é o ótimo (dois
blocos 2×2), também obtido por `guloso-trocas`, extensão da §21.13 oferecida
fora da campanha principal. Para o anel da figura 21.1, o linear custa
`30/16`, a serpentina `18/16` e o ciclo hamiltoniano `16/16`; esses valores
são para o tráfego ideal entre vizinhos, sem L2 nem diretórios.
