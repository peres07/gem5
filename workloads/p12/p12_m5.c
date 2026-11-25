// Copyright (c) 2026 The Project 12 contributors
// SPDX-License-Identifier: BSD-3-Clause

#define _GNU_SOURCE
#include <Python.h>
#include <sys/syscall.h>
#include <unistd.h>

#include "gem5/m5ops.h"

static PyObject *
cpu_atual(PyObject *self, PyObject *args)
{
    unsigned cpu;
    if (syscall(SYS_getcpu, &cpu, NULL, NULL) != 0)
        return PyErr_SetFromErrno(PyExc_OSError);
    return PyLong_FromUnsignedLong(cpu);
}

static PyObject *
abre_roi(PyObject *self, PyObject *args)
{
    m5_reset_stats(0, 0);
    Py_RETURN_NONE;
}

static PyObject *
fecha_roi(PyObject *self, PyObject *args)
{
    m5_dump_stats(0, 0);
    Py_RETURN_NONE;
}

static PyObject *
encerra(PyObject *self, PyObject *args)
{
    m5_exit(0);
    Py_RETURN_NONE;
}

static PyObject *
prepara(PyObject *self, PyObject *args)
{
    m5_work_begin(0, 0);
    Py_RETURN_NONE;
}

static PyMethodDef metodos[] = {
    {"prepara", prepara, METH_NOARGS, NULL},
    {"cpu_atual", cpu_atual, METH_NOARGS, NULL},
    {"abre_roi", abre_roi, METH_NOARGS, NULL},
    {"fecha_roi", fecha_roi, METH_NOARGS, NULL},
    {"encerra", encerra, METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef modulo = {
    PyModuleDef_HEAD_INIT,
    "_p12_m5",
    NULL,
    -1,
    metodos,
};

PyMODINIT_FUNC
PyInit__p12_m5(void)
{
    return PyModule_Create(&modulo);
}
