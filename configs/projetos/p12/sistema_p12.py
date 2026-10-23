"""Sistema X86 SE com Ruby/Garnet para o Projeto 12."""

import argparse
import os
import shlex

import m5
from m5.objects import *
from m5.util import addToPath

addToPath("../../")
from common import Options
from ruby import Ruby


ap = argparse.ArgumentParser()
Options.addCommonOptions(ap)
Options.addSEOptions(ap)
Ruby.define_options(ap)
ap.set_defaults(cpu_type="X86O3CPU")
ap.add_argument("--p12-mapa")
ap.add_argument("--p12-matriz", action="store_true")
ap.add_argument("--p12-helper")
args = ap.parse_args()

if not args.cmd or not os.path.isfile(args.cmd):
    ap.error("--cmd precisa apontar para um executavel existente")
if (args.num_cpus, args.mesh_rows) not in ((8, 2), (16, 4)):
    ap.error("use 8 nucleos/2 linhas ou 16 nucleos/4 linhas")
if args.num_l2caches != args.num_cpus or args.num_dirs != args.num_cpus:
    ap.error("L2 e diretorios devem ter um banco por nucleo")
if args.network != "garnet":
    ap.error("use --network=garnet")
if args.cpu_type not in ("X86TimingSimpleCPU", "X86O3CPU"):
    ap.error("use X86O3CPU ou X86TimingSimpleCPU")

system = System(mem_mode="timing", mem_ranges=[AddrRange(args.mem_size)])
system.voltage_domain = VoltageDomain(voltage=args.sys_voltage)
system.clk_domain = SrcClockDomain(
    clock=args.sys_clock, voltage_domain=system.voltage_domain
)
system.cache_line_size = args.cacheline_size

cpu_class = X86O3CPU if args.cpu_type == "X86O3CPU" else X86TimingSimpleCPU
system.cpu = [cpu_class(cpu_id=i) for i in range(args.num_cpus)]
for cpu in system.cpu:
    cpu.clk_domain = system.clk_domain

Ruby.create_system(args, False, system)
system.ruby.clk_domain = SrcClockDomain(
    clock=args.ruby_clock, voltage_domain=system.voltage_domain
)
system.ruby.network.p12_matriz = args.p12_matriz
for i, cpu in enumerate(system.cpu):
    cpu.createInterruptController()
    system.ruby._cpu_ports[i].connectCpuPorts(cpu)
    # Contextos extras terminam antes da ROI e ficam livres para clone().
    if i == 0:
        cmd = [args.cmd] + shlex.split(args.options or "")
    elif args.p12_helper:
        cmd = [args.p12_helper]
    else:
        cmd = [args.cmd, "--helper"]
    cpu.workload = Process(pid=100 + i, cmd=cmd)
    cpu.createThreads()

system.workload = SEWorkload.init_compatible(args.cmd)
root = Root(full_system=False, system=system)
m5.instantiate()
evento = m5.simulate()
print(f"Fim @ tick {m5.curTick()}: {evento.getCause()}")
