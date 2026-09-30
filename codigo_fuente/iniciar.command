#!/bin/bash
# Doble clic (Mac) para arrancar el Monitor en tiempo real.
# La primera vez quizas debas darle permiso: clic derecho -> Abrir.
cd "$(dirname "$0")"
python3 monitor.py serve
