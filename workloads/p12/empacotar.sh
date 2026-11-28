#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
set -euo pipefail

uso() {
    cat <<'EOF'
Uso: workloads/p12/empacotar.sh [DADOS [RELATORIO [FIGURAS [LOGS]]]]

DADOS: padrão docs/projeto12/dados, com os quatro CSV cpp-*.csv.
RELATORIO: fonte .tex, padrão
  docs/projeto12/relatorio/trabalho3_relatorio_final.tex.
FIGURAS: padrão DADOS/graficos. Referências LaTeX: ../dados/graficos/.
LOGS: padrão DADOS; copia apenas .log não ocultos. Use - para omitir.
Argumentos explícitos são relativos ao diretório de onde se chama o script.
Requer Bash, Git, pdflatex e pdfinfo (Poppler). Use PDFLATEX para
indicar outro executável de LaTeX.
Publica o diretório docs/projeto12/entrega/, não um ZIP. Não o sobrescreve.
EOF
}

falha() {
    printf 'empacotar: %s\n' "$*" >&2
    exit 1
}

# Nomes de experimentos que não fazem parte da entrega.
fora_do_escopo() {
    local nome=${1,,}
    local exclusoes='o3(cpu)?|prot[oó]tipo|prototype|hist[oó]rico'
    exclusoes+='|pessoal|privado'
    [[ $nome =~ (^|[/_.-])($exclusoes)([/_.-]|$) ||
        ${nome##*/} == comunicacao.py || $nome == */.* || $nome == .* ]]
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    uso
    exit 0
fi
if (( $# > 4 )); then
    uso >&2
    exit 2
fi

raiz=$(git -C "$(dirname -- "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
projeto=$raiz/docs/projeto12
destino=$projeto/entrega
dados=$(realpath -e -- "${1:-$projeto/dados}")
relatorio_padrao=$projeto/relatorio/trabalho3_relatorio_final.tex
relatorio=$(realpath -e -- "${2:-$relatorio_padrao}")
figuras=$(realpath -e -- "${3:-$dados/graficos}")
logs=${4:-$dados}
if [[ $logs != - ]]; then
    logs=$(realpath -e -- "$logs")
    [[ -d $logs ]] || falha 'LOGS precisa ser um diretório ou -.'
fi
[[ -f $relatorio && $relatorio == *.tex ]] ||
    falha 'Informe a fonte LaTeX atual (.tex).'
[[ -d $figuras ]] || falha 'O diretório de figuras não existe.'
for entrada in "$dados" "$relatorio" "$figuras" "$logs"; do
    if fora_do_escopo "${entrada#"$raiz"/}"; then
        falha "Entrada fora do escopo: $entrada."
    fi
done
[[ ! -L $projeto ]] || falha "$projeto não pode ser um link simbólico."
[[ ! -e $destino && ! -L $destino ]] || falha "Já existe $destino."
pdflatex=${PDFLATEX:-pdflatex}
for ferramenta in pdfinfo "$pdflatex"; do
    command -v "$ferramenta" >/dev/null || falha "Falta $ferramenta."
done

cd -- "$raiz"
export GIT_OPTIONAL_LOCKS=0
base=$(git rev-parse --verify '7a2b0e413d06c5ce7097104abef3b1d9eaabca91^{commit}')
mkdir -p -- "$projeto"
temporario=$(mktemp -d -- "$projeto/.empacotar.XXXXXXXX")
trap 'rm -rf -- "$temporario"' EXIT
pacote=$temporario/entrega
mkdir -- "$pacote"

opcoes_diff=(--binary --full-index --no-ext-diff --no-textconv --no-renames
             --src-prefix=a/ --dst-prefix=b/)

patch_do_projeto() {
    local saida=$1 caminho status
    local -a rastreados=() novos=()
    shift
    git diff --name-only --no-renames -z "$base" -- "$@" \
        > "$temporario/rastreados"
    git ls-files --others --exclude-standard -z -- "$@" \
        > "$temporario/novos"
    while IFS= read -r -d '' caminho; do
        if ! fora_do_escopo "$caminho"; then
            rastreados+=("$caminho")
        fi
    done < "$temporario/rastreados"
    while IFS= read -r -d '' caminho; do
        if ! fora_do_escopo "$caminho"; then
            novos+=("$caminho")
        fi
    done < "$temporario/novos"

    : > "$saida"
    if (( ${#rastreados[@]} )); then
        git --literal-pathspecs diff "${opcoes_diff[@]}" "$base" -- \
            "${rastreados[@]}" >> "$saida"
    fi
    for caminho in "${novos[@]}"; do
        [[ -f $caminho && ! -L $caminho ]] || falha "Arquivo: $caminho"
        if git cat-file -e "$base:$caminho" 2>/dev/null; then
            falha "$caminho existe na base, mas não está no índice atual."
        fi
        # --no-index inclui arquivos novos sem git add nem banco de objetos.
        status=0
        git diff --no-index "${opcoes_diff[@]}" -- /dev/null "$caminho" \
            >> "$saida" || status=$?
        # Em --no-index, 1 significa "há diferenças", não erro.
        (( status <= 1 )) || falha "Não foi possível incluir $caminho."
    done
    [[ -s $saida ]] || falha "Patch vazio: ${saida##*/}."
}

garnet=(':(glob)src/mem/ruby/network/garnet/**/*.cc'
        ':(glob)src/mem/ruby/network/garnet/**/*.hh'
        ':(glob)src/mem/ruby/network/garnet/**/*.py'
        ':(glob)src/mem/ruby/network/garnet/**/SConscript'
        src/mem/ruby/slicc_interface/Message.hh)
patch_do_projeto "$pacote/garnet.diff" "${garnet[@]}"
patch_do_projeto "$temporario/configs-workloads.patch" \
    configs/example/garnet_synth_traffic.py configs/topologies/MeshMapeada.py \
    ':(glob)configs/projetos/p12/**/*.py' \
    ':(glob)configs/projetos/p12/**/*.sh' \
    ':(glob)workloads/p12/**/*.cc' ':(glob)workloads/p12/**/*.hh' \
    ':(glob)workloads/p12/**/*.h' ':(glob)workloads/p12/**/*.py' \
    ':(glob)workloads/p12/**/*.sh' workloads/p12/{Makefile,README.md}
cat -- "$pacote/garnet.diff" "$temporario/configs-workloads.patch" \
    > "$pacote/projeto12.patch"

# Valida a aplicação contra a base, não contra o checkout modificado.
(
    export GIT_INDEX_FILE=$temporario/indice-base
    git -c core.splitIndex=false read-tree "$base"
    git -c core.splitIndex=false apply --check --cached -- \
        "$pacote/projeto12.patch"
)

copiar_lista() {
    local origem=$1 destino_local=$2 arquivo relativo
    shift 2
    [[ -d $origem ]] || return 0
    find "$origem" -type f \( "$@" \) -print0 > "$temporario/lista"
    while IFS= read -r -d '' arquivo; do
        relativo=${arquivo#"$origem"/}
        if fora_do_escopo "/$relativo"; then
            continue
        fi
        mkdir -p -- "$(dirname -- "$destino_local/$relativo")"
        cp -- "$arquivo" "$destino_local/$relativo"
    done < "$temporario/lista"
}

mkdir -- "$pacote/dados"
for tabela in metricas referencias estabilidade segundo-perfil; do
    origem=$dados/cpp-$tabela.csv
    [[ -f $origem && ! -L $origem && -s $origem ]] ||
        falha "CSV ausente ou inválido: $origem"
    cp -- "$origem" "$pacote/dados/"
done
for nota in ORIGEM.md conferencia.md; do
    arquivo=$dados/$nota
    if [[ -f $arquivo && ! -L $arquivo ]]; then
        cp -- "$arquivo" "$pacote/dados/"
    fi
done
copiar_lista "$dados/analise" "$pacote/dados/analise" -name '*.csv'
copiar_lista "$projeto/validacao" "$pacote/validacao" \
    -name '*.md' -o -name '*.txt' -o -name '*.log' -o -name '*.json' \
    -o -name '*.csv'
copiar_lista "$figuras" "$pacote/dados/graficos" \
    -iname '*.png' -o -iname '*.pdf' -o -iname '*.svg' -o \
    -iname '*.jpg' -o -iname '*.jpeg'
[[ -d $pacote/dados/graficos ]] || falha 'Nenhuma figura elegível.'
if [[ $logs != - ]]; then
    copiar_lista "$logs" "$pacote/logs" -name '*.log'
fi

# Compilar a cópia garante que as figuras do pacote bastam para o relatório.
nome_tex=${relatorio##*/}
copiar_lista "$(dirname -- "$relatorio")" "$pacote/relatorio" \
    -name '*.tex' -o -name '*.bib' -o -name '*.sty' -o -name '*.cls'
[[ -f $pacote/relatorio/$nome_tex ]] || falha 'Fonte LaTeX fora do escopo.'
mkdir -- "$temporario/latex"
(
    cd -- "$pacote/relatorio"
    for passada in 1 2; do
        "$pdflatex" -no-shell-escape -halt-on-error -interaction=nonstopmode \
            -output-directory="$temporario/latex" "./$nome_tex"
    done
)
pdf=$temporario/latex/${nome_tex%.tex}.pdf
paginas=$(LC_ALL=C pdfinfo "$pdf" | awk '$1 == "Pages:" { print $2 }')
[[ $paginas =~ ^[678]$ ]] || falha "Esperava 6–8 páginas; obtive $paginas."
cp -- "$pdf" "$pacote/relatorio.pdf"

cat > "$pacote/LEIA-ME.txt" <<EOF
Projeto 12 — entrega

relatorio.pdf  Relatório LaTeX ($paginas páginas).
relatorio/  Fontes LaTeX; compile $nome_tex a partir desse diretório.
projeto12.patch  Patch completo (inclui Garnet, configs e workloads C++).
garnet.diff  Subconjunto do patch, para leitura isolada; não aplique os dois.
dados/  CSV originais da campanha C++, conferência (se houver) e gráficos.
dados/graficos/  Figuras referenciadas pelas fontes LaTeX.
validacao/  Evidências disponíveis de validação, quando presentes.
logs/  Logs opcionais do diretório informado, quando presentes.

Em um checkout limpo do gem5 na base $base, a partir da raiz:
  git apply --check /caminho/da/entrega/projeto12.patch
  git apply /caminho/da/entrega/projeto12.patch

O patch representa os arquivos do diretório de trabalho no momento do
empacotamento, não apenas HEAD. Git não precisa ser alterado para gerar a
entrega. Veja workloads/p12/README.md no código reconstruído para os passos
de compilação, execução e validação.
EOF

mv -T -n -- "$pacote" "$destino"
[[ ! -e $pacote ]] || falha "Já existe $destino."
printf 'Entrega pronta: %s\n' "$destino"
