# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Compara as topologias em X86 SE e verifica a troca das L1 0 e 5."""

import argparse
import json
from configparser import ConfigParser

from fluxo_p12 import (
    ERROS_DADOS,
    PROGRAMAS,
    adiciona_opcoes,
    configura,
    escreve_json,
)
from valida_sintetico_p12 import compara


def enlaces_externos(pasta):
    ini = ConfigParser(interpolation=None)
    with (pasta / "config.ini").open() as arq:
        ini.read_file(arq)
    return {
        config["ext_node"].rsplit(".", 1)[-1]: int(
            ini[config["int_node"]]["router_id"]
        )
        for nome in ini.sections()
        if nome.startswith("system.ruby.network.ext_links")
        and "ext_node" in (config := ini[nome])
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    adiciona_opcoes(ap)
    args = ap.parse_args()
    fluxo = configura(ap, args)
    pasta = fluxo.saida / "validacao-x86"
    semente = args.semente_perfil
    try:
        for prog in PROGRAMAS:
            xy = pasta / prog / "xy"
            mapeada = pasta / prog / "mapeada"
            fluxo.roda(xy, prog, 16, semente, topologia="Mesh_XY")
            fluxo.roda(mapeada, prog, 16, semente)
            compara(xy, mapeada)
            if enlaces_externos(xy) != enlaces_externos(mapeada):
                raise ValueError(f"enlaces externos diferentes: {prog}")

        prof = pasta / "vizinhanca" / "mapeada"
        linear = fluxo.mapeia(prof, "linear", 0, 16)
        repeticao = pasta / "vizinhanca" / "linear-json"
        fluxo.roda(repeticao, "vizinhanca", 16, semente, linear)
        compara(prof, repeticao)

        dados = json.loads(linear.read_text())
        dados.update(politica="troca-teste", distancia_prevista=None)
        mapa = dados["mapa"]
        mapa["l1_cntrl0"], mapa["l1_cntrl5"] = (
            mapa["l1_cntrl5"],
            mapa["l1_cntrl0"],
        )
        troca = pasta / "troca-0-5.json"
        escreve_json(troca, dados)
        aval = pasta / "vizinhanca" / "troca-0-5"
        fluxo.roda(aval, "vizinhanca", 16, semente, troca)
        if enlaces_externos(aval) != mapa:
            raise ValueError(
                "a troca nao corresponde aos enlaces de config.ini"
            )
    except ERROS_DADOS as erro:
        ap.exit(1, f"Falha: {erro}; veja {pasta}\n")
    print(f"Validacao X86 OK: {pasta}")


if __name__ == "__main__":
    main()
