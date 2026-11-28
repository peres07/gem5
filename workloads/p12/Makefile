# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

GEM5_ROOT ?= ../..
OUT ?= $(GEM5_ROOT)/build/workloads/p12
M5_LIB ?= $(GEM5_ROOT)/util/m5/build/x86/out/libm5.a
CXXFLAGS ?= -O2 -g -Wall -Wextra
PROGRAMAS := $(addprefix $(OUT)/,vizinhanca grupos uniforme)

.PHONY: all check
all: $(PROGRAMAS)

$(M5_LIB):
	cd $(GEM5_ROOT)/util/m5 && scons build/x86/out/libm5.a

$(OUT)/%: %.cc comum.h $(M5_LIB)
	mkdir -p $(@D)
	$(CXX) $(CPPFLAGS) -I$(GEM5_ROOT)/include $(CXXFLAGS) -std=c++17 \
	    -march=x86-64 -pthread -static $(LDFLAGS) $< $(M5_LIB) $(LDLIBS) -o $@

check: all
	@set -e; for n in 8 16; do \
	    for programa in $(PROGRAMAS); do $$programa $$n 12 3 11 --nativo; done; \
	    $(OUT)/grupos $$n 12 3 11 --nativo --blocos; \
	done
