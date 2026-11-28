#!/usr/bin/env bash
# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

set -euo pipefail

uso() {
    cat <<'EOF'
Uso: workloads/p12/reproduzir.sh [opções]

Campanha C++ com X86TimingSimpleCPU e MESI_Two_Level: 6 perfis,
99 avaliações, 6 perfis de estabilidade, 18 avaliações do segundo guloso
e 4 gráficos PNG. As tabelas derivadas ficam em saida/tabelas/.
O roteiro roda as cargas no hospedeiro e confere os checksums simulados.

  --saida DIR             Resultados (padrão: m5out/p12 no repositório).
  --gem5 ARQUIVO          Usar binário existente; não rodar SCons do gem5.
  --workloads DIR         Usar executáveis existentes; não rodar make/libm5.
  --jobs N                Simulações em paralelo (padrão: 1).
  --jobs-build N          Paralelismo de compilação (padrão: 2).
  --iteracoes N           Iterações por thread (padrão: 10).
  --linhas-mensagem N     Linhas de cache por mensagem (padrão: 4).
  --semente-perfil N      Semente para os perfis (padrão: 1).
  --flits-transito N      Limite de flits em trânsito (padrão: 32).
  --listar                Validar a configuração e listar a campanha, sem
                          compilar, simular ou criar a saída.
  -h, --help              Mostrar esta ajuda.

Caminhos fornecidos são relativos ao diretório de chamada. Sem --gem5 e
--workloads, usa SCons em build/X86 e make para os três workloads. Não
modifique os binários durante a execução. A mesma saída retoma casos
válidos; use outra saída para preservar campanhas com parâmetros distintos.
O python3 do PATH deve ter matplotlib instalado.
Cada tentativa registra comandos, tempos e versões em saida/reproducao/.
Um manifesto com estado=concluido indica o sucesso daquela tentativa.
EOF
}

falha() {
    printf 'reproduzir: %s\n' "$*" >&2
    exit 1
}

raiz=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
saida="$raiz/m5out/p12"
gem5="$raiz/build/X86/gem5.opt"
workloads="$raiz/build/workloads/p12"
compila_gem5=1
compila_workloads=1
jobs=1
jobs_build=2
iteracoes=10
linhas=4
semente=1
transito=32
listar=0

while (( $# )); do
    case $1 in
        -h|--help) uso; exit 0 ;;
        --listar) listar=1; shift; continue ;;
        --saida|--gem5|--workloads|--jobs|--jobs-build|--iteracoes|\
        --linhas-mensagem|--semente-perfil|--flits-transito)
            [[ -n ${2:-} && $2 != --* ]] || falha "falta valor para $1"
            ;;
        *) falha "opção desconhecida: $1 (veja --help)" ;;
    esac
    case $1 in
        --saida) saida=$2 ;;
        --gem5) gem5=$2; compila_gem5=0 ;;
        --workloads) workloads=$2; compila_workloads=0 ;;
        --jobs) jobs=$2 ;;
        --jobs-build) jobs_build=$2 ;;
        --iteracoes) iteracoes=$2 ;;
        --linhas-mensagem) linhas=$2 ;;
        --semente-perfil) semente=$2 ;;
        --flits-transito) transito=$2 ;;
    esac
    shift 2
done

[[ $jobs_build =~ ^[1-9][0-9]*$ ]] || falha '--jobs-build deve ser positivo'
saida=$(realpath -m -- "$saida")
if (( ! compila_gem5 )); then gem5=$(realpath -m -- "$gem5"); fi
if (( ! compila_workloads )); then workloads=$(realpath -m -- "$workloads"); fi
cd -- "$raiz"
export PYTHONDONTWRITEBYTECODE=1

config=configs/projetos/p12
programas=(vizinhanca grupos uniforme)
opcoes=(--saida="$saida" --gem5="$gem5" --workloads="$workloads" --jobs="$jobs"
    --iteracoes="$iteracoes" --linhas-mensagem="$linhas"
    --semente-perfil="$semente" --flits-transito="$transito")
campanha=(python3 "$config/campanha_p12.py" --fase todas --estabilidade
    "${opcoes[@]}")
plano=$("${campanha[@]}" --listar)
[[ $plano == '6 perfis; 99 avaliacoes' ]] || falha "plano inesperado: $plano"
printf '%s (+6 perfis de estabilidade e 18 avaliações do segundo perfil)\n' \
    "$plano"
if (( listar )); then
    exit 0
fi

executavel() {
    [[ -f $1 && -x $1 ]] || falha "executável não encontrado: $1"
}

if (( ! compila_gem5 )); then
    executavel "$gem5"
fi
if (( ! compila_workloads )); then
    for prog in "${programas[@]}"; do executavel "$workloads/$prog"; done
fi

mkdir -p -- "$saida/reproducao"
exec {trava_saida}>>"$saida/reproducao/.lock"
flock -n "$trava_saida" || falha "saída em uso: $saida"
if (( compila_gem5 || compila_workloads )); then
    mkdir -p build
    exec {trava_build}>>build/.p12-reproducao.lock
    flock -n "$trava_build" || falha 'build em uso por outra reprodução'
fi

auditoria=$(mktemp -d "$saida/reproducao/execucao.XXXXXXXX")
manifesto="$auditoria/manifesto.txt"
inicio=$SECONDS
etapa=preparacao

finaliza() {
    local rc=$?
    trap - EXIT
    {
        printf 'fim_utc=%s\nelapsed_total_s=%s\ncodigo_saida=%s\n' \
            "$(date -u +%FT%TZ)" "$((SECONDS - inicio))" "$rc"
        if (( rc )); then
            printf 'etapa_falha=%s\nestado=falhou\n' "$etapa"
        else
            printf 'estado=concluido\n'
        fi
    } >> "$manifesto"
    if (( rc )); then
        printf 'Falha em %s. Veja %s\n' "$etapa" "$auditoria" >&2
    fi
    exit "$rc"
}
trap finaliza EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

registra() {
    local chave=$1
    shift
    printf '%s=' "$chave" >> "$manifesto"
    printf ' %q' "$@" >> "$manifesto"
    printf '\n' >> "$manifesto"
}

roda() {
    etapa=$1
    shift
    local t=$SECONDS rc=0 log="$auditoria/$etapa.log"
    registra "comando_$etapa" "$@"
    printf '%s → %s\n' "$etapa" "$log"
    "$@" > "$log" 2>&1 || rc=$?
    printf 'elapsed_%s_s=%s\n' "$etapa" "$((SECONDS - t))" >> "$manifesto"
    if (( rc )); then tail -n 20 -- "$log" >&2; fi
    return "$rc"
}

{
    printf 'inicio_utc=%s\n' "$(date -u +%FT%TZ)"
    printf 'cpu=X86TimingSimpleCPU\nprotocolo=MESI_Two_Level\n'
    printf 'compila_gem5=%s\ncompila_workloads=%s\n' \
        "$compila_gem5" "$compila_workloads"
} > "$manifesto"
commit=$(git rev-parse HEAD)
printf 'commit=%s\n' "$commit" >> "$manifesto"
registra diretorio_fonte "$raiz"
registra saida "$saida"
registra gem5 "$gem5"
registra workloads "$workloads"
git status --short --untracked-files=normal > "$auditoria/git-status.txt"
uname -a > "$auditoria/host.txt"
roda python python3 --version
roda matplotlib python3 -c 'import matplotlib; print(matplotlib.__version__)'

if (( compila_gem5 || compila_workloads )); then
    roda scons_versao scons --version
    roda cc_versao "${CC:-gcc}" --version
    roda cxx_versao "${CXX:-g++}" --version
    for var in CC CXX CCFLAGS_EXTRA GEM5PY_CCFLAGS_EXTRA \
        GEM5PY_LINKFLAGS_EXTRA LINKFLAGS_EXTRA MAKEFLAGS SCONSFLAGS \
        CPPFLAGS CXXFLAGS LDFLAGS LDLIBS; do
        registra "env_$var" "${!var-}"
    done
fi
if (( compila_workloads )); then
    roda make_versao make --version
    # Guarda as receitas e flags resolvidas mesmo se make não recompilar.
    roda workloads_flags make -C workloads/p12 -nB \
        -o ../../util/m5/build/x86/out/libm5.a all
fi
if (( compila_gem5 )); then
    etapa=config_x86
    kconfig=build/X86/gem5.build/config
    if [[ -e $kconfig ]]; then
        cp -- "$kconfig" "$auditoria/config-x86-antes.txt"
        for flag in USE_X86_ISA=y RUBY=y RUBY_PROTOCOL_MESI_Two_Level=y \
            'PROTOCOL="MESI_Two_Level"'; do
            grep -Fxq -- "$flag" "$kconfig" ||
                falha "$kconfig não contém $flag; não será alterado"
        done
    fi
    roda gem5_build scons --ignore-style --verbose -j "$jobs_build" build/X86/gem5.opt
    cp -- "$kconfig" "$auditoria/config-x86.txt"
fi

etapa=verifica_gem5
executavel "$gem5"
# --build-info tem a versão e o Kconfig embutido no executável real.
roda gem5_info "$gem5" -d "$auditoria" --build-info
grep -Fxq 'gem5 version 25.1.0.0' "$auditoria/gem5_info.log" ||
    falha 'Use um gem5 25.1.0.0 com o Projeto 12'
for flag in '^ +USE_X86_ISA = True$' '^ +RUBY = True$' \
    '^ +RUBY_PROTOCOL_MESI_Two_Level = True$' \
    '^ +PROTOCOL = MESI_Two_Level$'; do
    grep -Eq -- "$flag" "$auditoria/gem5_info.log" ||
        falha "gem5 não tem a configuração X86/MESI exigida ($flag)"
done
roda gem5_p12 "$gem5" -d "$auditoria" -c \
    'from m5.objects import GarnetNetwork, X86TimingSimpleCPU
if "p12_matriz" not in GarnetNetwork._params:
    raise SystemExit("gem5 não contém a instrumentação do Projeto 12")'

if (( compila_workloads )); then
    roda libm5_build scons -C util/m5 -j "$jobs_build" build/x86/out/libm5.a
    roda workloads_build make -C workloads/p12 -j "$jobs_build" all
fi
etapa=verifica_binarios
binarios=("$gem5")
for prog in "${programas[@]}"; do
    executavel "$workloads/$prog"
    binarios+=("$workloads/$prog")
done
if (( compila_workloads )); then
    binarios+=("$raiz/util/m5/build/x86/out/libm5.a")
fi
sha256sum -- "${binarios[@]}" > "$auditoria/binarios.sha256"

roda campanha "${campanha[@]}"
etapa=verifica_csv
python3 - "$saida" <<'PY'
import csv
import sys
from pathlib import Path

pasta = Path(sys.argv[1])
for nome, esperado in (
    ("metricas", 99), ("estabilidade", 6), ("referencias", 6)
):
    with (pasta / f"{nome}.csv").open(newline="") as arquivo:
        total = sum(1 for _ in csv.DictReader(arquivo))
    if total != esperado:
        sys.exit(f"{nome}.csv: {total} registros, esperados {esperado}")
PY

roda segundo_perfil python3 "$config/segundo_perfil_p12.py" "${opcoes[@]}"
roda confere_nativos python3 "$config/valida_nativos_p12.py" \
    --saida "$saida" --workloads "$workloads" --iteracoes "$iteracoes" \
    --linhas-mensagem "$linhas" --semente-perfil "$semente"
roda tabelas python3 "$config/relatorio_p12.py" --campanha "$saida" \
    --matrizes "$saida" --saida "$saida/tabelas"
roda graficos python3 "$config/analisa_p12.py" "$saida/metricas.csv" \
    --saida "$saida/graficos"
etapa=verifica_graficos
for nome in distancia latencia tempo saltos_tempo; do
    [[ -s $saida/graficos/$nome.png ]] || falha "gráfico ausente: $nome.png"
done

printf 'Resultados: %s\nManifesto: %s\n' "$saida" "$manifesto"
