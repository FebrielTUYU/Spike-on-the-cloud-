#!/usr/bin/env python3
"""Compara el primer arranque de monitor.py y Spike.exe con datos reales.

Uso desde la carpeta codigo_fuente:
  python test_arranque_tiempos.py --exe dist_compilado/Spike.dist/Spike.exe

Ejecuta primero Python y luego el ejecutable, sin solaparlos. Ambos procesos
usan HERE y los datos de su carpeta de trabajo, igual que al abrir la app.
La corrida puede modificar data.json, historias_registro.json y caches; hacer
una copia de seguridad antes de usarla sobre datos que se quieran preservar.
El proceso de serve se detiene al registrar la primera pasada completa.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent
DONE_MARKER = "primera pasada terminada"


def puerto_libre() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def historias_publicadas(url: str) -> int | None:
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            data = json.load(response)
        return len(data.get("historias") or [])
    except (OSError, ValueError, urllib.error.URLError):
        return None


def ejecutar(nombre: str, command: list[str], cwd: Path, timeout: float,
             log: Path) -> dict:
    # El ejecutable puede ser GUI y no heredar stdout; el log persistente es
    # la fuente común de hitos para ambos modos.
    try:
        log.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError(f"No se pudo limpiar {log}: {exc}") from exc

    port = puerto_libre()
    cmd = command + ["serve", str(port)]
    started = time.monotonic()
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    first_news = None
    stories_count = 0
    complete = None
    error = None
    try:
        while time.monotonic() - started < timeout:
            elapsed = time.monotonic() - started
            if proc.poll() is not None:
                error = f"el proceso terminó antes del hito (código {proc.returncode})"
                break
            count = historias_publicadas(f"http://127.0.0.1:{port}/data.json")
            if count and first_news is None:
                first_news, stories_count = elapsed, count
            try:
                content = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = ""
            if DONE_MARKER in content:
                complete = elapsed
                break
            time.sleep(0.25)
        else:
            error = f"timeout de {timeout:g}s sin completar la primera pasada"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    result = {"modo": nombre, "comando": cmd, "seg_hasta_noticias": first_news,
              "historias_observadas": stories_count, "seg_corrida_completa": complete,
              "error": error}
    print(json.dumps(result, ensure_ascii=False))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", dest="python_exe", default=sys.executable,
                        help="intérprete Python (por defecto, el actual)")
    parser.add_argument("--script", type=Path, default=ROOT / "monitor.py")
    parser.add_argument("--exe", type=Path, required=True,
                        help="ruta a Spike.exe compilado con el mismo código")
    parser.add_argument("--cwd", type=Path, default=ROOT,
                        help="carpeta de datos/HERE; debe ser la misma en ambos modos")
    parser.add_argument("--timeout", type=float, default=3600,
                        help="máximo de segundos por modo (default: 3600)")
    args = parser.parse_args()
    cwd = args.cwd.resolve()
    script, exe = args.script.resolve(), args.exe.resolve()
    if not script.is_file() or not exe.is_file():
        parser.error("--script o --exe no existe")
    log = cwd / "arranque.log"
    results = [
        ejecutar("python", [str(Path(args.python_exe).resolve()), str(script)],
                 cwd, args.timeout, log),
        ejecutar("exe", [str(exe)], cwd, args.timeout, log),
    ]
    print("\nResumen (segundos):")
    print("modo\tnoticias\tcorrida_completa\terror")
    for item in results:
        print(f"{item['modo']}\t{item['seg_hasta_noticias']}\t"
              f"{item['seg_corrida_completa']}\t{item['error'] or '-'}")
    return 0 if all(x["error"] is None and x["seg_hasta_noticias"] is not None
                    and x["seg_corrida_completa"] is not None for x in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
