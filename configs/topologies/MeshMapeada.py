"""Mesh_XY com posicoes configuraveis para controladores L1."""

import json
from pathlib import Path

from topologies.Mesh_XY import Mesh_XY


class MeshMapeada(Mesh_XY):
    description = "MeshMapeada"

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        # Mantem os roteadores, enlaces e a ordem original da Mesh_XY.
        super().makeTopology(options, network, IntLink, ExtLink, Router)
        arquivo = getattr(options, "p12_mapa", None)
        if not arquivo:
            return

        dados = json.loads(Path(arquivo).read_text())
        mapa = dados.get("mapa")
        if not isinstance(mapa, dict):
            raise ValueError("P12: JSON sem objeto 'mapa'")
        base = {
            link.ext_node.path().rsplit(".", 1)[-1]: int(link.int_node.router_id)
            for link in network.ext_links
        }
        if set(mapa) != set(base):
            raise ValueError("P12: mapa deve conter todos os controladores, sem extras")
        l1 = [nome for nome in base if nome.startswith("l1_cntrl")]
        if len(l1) != options.num_cpus:
            raise ValueError("P12: numero de L1 diferente do numero de nucleos")
        if any(type(r) is not int or r < 0 or r >= options.num_cpus
               for r in mapa.values()):
            raise ValueError("P12: roteador invalido no mapa")
        if any(mapa[nome] != base[nome] for nome in base if nome not in l1):
            raise ValueError("P12: apenas controladores L1 podem mudar")
        if sorted(mapa[nome] for nome in l1) != list(range(options.num_cpus)):
            raise ValueError("P12: precisa haver uma L1 por roteador")
        for link in network.ext_links:
            nome = link.ext_node.path().rsplit(".", 1)[-1]
            if nome in l1:
                link.int_node = network.routers[mapa[nome]]
