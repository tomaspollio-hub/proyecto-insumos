#!/usr/bin/env python3
"""
Enriquece el CSV exportado desde Isumos con descripción e imagen de producto.

Fuente: Open Food Facts (gratuito, sin API key)

Uso:
    python3 tools/enriquecer_productos.py catalogo.csv [directorio_salida]

Entrada:  CSV con al menos columna 'codigo_barras'
Salida:
    output/catalogo_enriquecido.csv   — mismo CSV + columna 'descripcion' completa
    output/imagenes/<barcode>.jpg     — imágenes descargadas (nombradas por barcode)
    output/sin_datos.txt              — barcodes no encontrados en ninguna fuente
"""

import csv
import sys
import time
from pathlib import Path

import requests

OFF_URL    = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OFF_FIELDS = "product_name,brands,generic_name,image_front_url,quantity,packaging"
HEADERS    = {"User-Agent": "Isumos-Enricher/1.0 (tomaspollio@gmail.com)"}
DELAY      = 0.6  # segundos entre requests (respeta rate limit de OFF)


def _buscar_off(barcode: str) -> dict | None:
    try:
        r = requests.get(
            OFF_URL.format(barcode=barcode),
            params={"fields": OFF_FIELDS},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return data.get("product") if data.get("status") == 1 else None
    except Exception:
        return None


def _descargar_imagen(url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
        if r.status_code == 200:
            dest.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False


def _descripcion(producto: dict) -> str:
    for campo in ("generic_name", "product_name", "brands"):
        valor = (producto.get(campo) or "").strip()
        if valor:
            return valor
    return ""


def enriquecer(input_csv: str, output_dir: str = "output") -> None:
    src = Path(input_csv)
    if not src.exists():
        print(f"Error: no existe el archivo '{input_csv}'")
        sys.exit(1)

    out = Path(output_dir)
    img_dir = out / "imagenes"
    img_dir.mkdir(parents=True, exist_ok=True)

    with open(src, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("El CSV está vacío.")
        sys.exit(0)

    fieldnames = list(rows[0].keys())
    if "descripcion" not in fieldnames:
        fieldnames.append("descripcion")
    if "imagen_local" not in fieldnames:
        fieldnames.append("imagen_local")

    sin_datos: list[str] = []
    out_rows: list[dict] = []

    for i, row in enumerate(rows, 1):
        barcode = (row.get("codigo_barras") or "").strip()
        nombre  = (row.get("nombre") or "")[:45]
        print(f"[{i:>4}/{len(rows)}] {barcode:<14} {nombre:<45}", end=" ")

        producto   = _buscar_off(barcode) if barcode else None
        img_path   = ""

        if producto:
            desc    = _descripcion(producto)
            img_url = (producto.get("image_front_url") or "").strip()

            if img_url:
                ext  = Path(img_url.split("?")[0]).suffix or ".jpg"
                dest = img_dir / f"{barcode}{ext}"
                ok   = _descargar_imagen(img_url, dest)
                img_path = str(dest.relative_to(out)) if ok else ""

            row["descripcion"] = desc
            row["imagen_local"] = img_path
            status = "OK" + (" + img" if img_path else "     ")
        else:
            row.setdefault("descripcion", "")
            row.setdefault("imagen_local", "")
            sin_datos.append(barcode)
            status = "NO ENCONTRADO"

        print(status)
        out_rows.append(row)
        time.sleep(DELAY)

    # CSV enriquecido
    out_csv = out / f"{src.stem}_enriquecido.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)

    # Lista de no encontrados
    if sin_datos:
        (out / "sin_datos.txt").write_text("\n".join(sin_datos), encoding="utf-8")

    encontrados = len(rows) - len(sin_datos)
    print(f"\n{'─'*60}")
    print(f"Encontrados:     {encontrados}/{len(rows)}")
    print(f"CSV enriquecido: {out_csv}")
    print(f"Imágenes:        {img_dir}/")
    if sin_datos:
        print(f"Sin datos ({len(sin_datos)}):  {out}/sin_datos.txt")
    print()
    print("Próximos pasos:")
    print("  1. Revisá y completá manualmente las filas en sin_datos.txt")
    print("  2. Importá el CSV desde Admin → Catálogo → Importar CSV")
    print("  3. Subí las imágenes desde Admin → Catálogo → Carga masiva de imágenes")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    input_csv  = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
    enriquecer(input_csv, output_dir)
