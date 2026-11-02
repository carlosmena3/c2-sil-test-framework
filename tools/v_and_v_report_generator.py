#!/usr/bin/env python3
"""Generador de reporte formal de Verificación y Validación (V&V)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DOORS_MARK_PATTERN: re.Pattern[str] = re.compile(
    r'req_id[=:]\s*["\']?(REQ-[A-Z0-9_\-]+)["\']?'
)


def load_pytest_report(report_path: Path) -> dict[str, Any]:
    """Carga el reporte JSON generado por pytest-json-report."""
    if not report_path.exists():
        raise FileNotFoundError(f"Reporte de pytest no encontrado: {report_path}")
    with report_path.open(encoding="utf-8") as f:
        return json.load(f)


def load_requirements_csv(csv_path: Path) -> dict[str, dict[str, str]]:
    """Carga los requisitos desde el CSV de DOORS."""
    reqs: dict[str, dict[str, str]] = {}
    if not csv_path.exists():
        return reqs
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            req_id = row.get("Req_ID", "").strip()
            if req_id:
                reqs[req_id] = dict(row)
    return reqs


def extract_doors_marks_from_report(
    tests: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Extrae las asociaciones Req_ID -> tests desde los metadatos del reporte."""
    req_to_tests: dict[str, list[str]] = {}
    for test in tests:
        markers: list[dict[str, Any]] = test.get("markers", [])
        for marker in markers:
            if marker.get("name") == "doors":
                kwargs: dict[str, Any] = marker.get("kwargs", {})
                req_id: str = kwargs.get("req_id", "")
                if req_id:
                    req_to_tests.setdefault(req_id, []).append(
                        test.get("nodeid", "?")
                    )
    return req_to_tests


def outcome_badge(outcome: str) -> str:
    """Convierte el resultado de ejecución en etiqueta de texto legible."""
    mapping = {
        "passed": "[PASS]",
        "failed": "[FAIL]",
        "error": "[ERROR]",
        "skipped": "[SKIP]",
        "xfailed": "[XFAIL]",
        "xpassed": "[XPASS]",
    }
    return mapping.get(outcome.lower(), outcome.upper())


def generate_markdown_report(
    pytest_data: dict[str, Any],
    req_to_tests: dict[str, list[str]],
    requirements: dict[str, dict[str, str]],
    output_path: Path,
) -> None:
    """Genera el informe V&V en formato Markdown."""
    summary: dict[str, Any] = pytest_data.get("summary", {})
    tests: list[dict[str, Any]] = pytest_data.get("tests", [])
    created_at: str = pytest_data.get("created", "N/A")
    duration_s: float = pytest_data.get("duration", 0.0)

    total = summary.get("total", len(tests))
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    errors = summary.get("error", 0)
    skipped = summary.get("skipped", 0)

    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    lines: list[str] = [
        "# Informe Formal de Verificación y Validación (V&V)",
        "",
        f"**Proyecto:** Sistema ATM / Mando y Control – Suite SIL  ",
        f"**Fecha de ejecución:** {created_at}  ",
        f"**Generado:** {now_str}  ",
        f"**Normas aplicables:** EUROCAE ED-153 / DO-178C / EUROCONTROL ESARR6  ",
        "",
        "---",
        "",
        "## 1. Resumen Ejecutivo",
        "",
        "| Métrica | Valor |",
        "|---------|-------|",
        f"| Total de casos de prueba | **{total}** |",
        f"| Aprobados (PASS) | **{passed}** |",
        f"| Fallidos (FAIL) | **{failed}** |",
        f"| Errores (ERROR) | **{errors}** |",
        f"| Omitidos (SKIP) | **{skipped}** |",
        f"| Tasa de aprobación | **{pass_rate:.1f}%** |",
        f"| Duración total | **{duration_s:.3f} s** |",
        "",
        "> **Veredicto global:** "
        + ("APROBADO" if failed == 0 and errors == 0 else "NO APROBADO"),
        "",
        "---",
        "",
        "## 2. Resultados por Caso de Prueba",
        "",
        "| # | Caso de Prueba | Estado | Duración (ms) |",
        "|---|---------------|--------|---------------|",
    ]

    for idx, test in enumerate(tests, start=1):
        node_id: str = test.get("nodeid", "?")
        outcome: str = test.get("outcome", "?")
        dur: float = test.get("duration", 0.0) * 1000.0
        lines.append(
            f"| {idx} | `{node_id}` | {outcome_badge(outcome)} | {dur:.1f} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 3. Cobertura de Requisitos DOORS",
        "",
        "| Req_ID | Safety | Sistema | Tests Asociados | Cobertura |",
        "|--------|--------|---------|-----------------|-----------|",
    ]

    covered_count = 0
    total_reqs = len(requirements) if requirements else len(req_to_tests)

    all_req_ids = set(requirements.keys()) if requirements else set(req_to_tests.keys())
    for req_id in sorted(all_req_ids):
        req_data = requirements.get(req_id, {})
        safety = req_data.get("Safety_Level", "N/A")
        system = req_data.get("Allocated_System", "N/A")
        associated = req_to_tests.get(req_id, [])
        coverage = "Cubierto" if associated else "Huérfano"
        if associated:
            covered_count += 1
        test_list = f"{len(associated)} test(s)" if associated else "—"
        lines.append(
            f"| `{req_id}` | {safety} | {system} | {test_list} | {coverage} |"
        )

    coverage_pct = (covered_count / total_reqs * 100) if total_reqs > 0 else 0.0
    lines += [
        "",
        f"**Cobertura de requisitos: {covered_count}/{total_reqs} ({coverage_pct:.1f}%)**",
        "",
        "---",
        "",
        "## 4. No Conformidades",
        "",
    ]

    failed_tests = [t for t in tests if t.get("outcome") in ("failed", "error")]
    if failed_tests:
        lines.append(
            f"Se detectaron **{len(failed_tests)}** no conformidad(es):\n"
        )
        for test in failed_tests:
            node_id = test.get("nodeid", "?")
            call_info = test.get("call", {})
            longrepr = call_info.get("longrepr", "Sin detalle disponible.")
            lines += [
                f"### NC: `{node_id}`",
                "",
                "```",
                str(longrepr)[:1000],
                "```",
                "",
            ]
    else:
        lines.append("**No se detectaron no conformidades en esta ejecución.**")

    lines += [
        "",
        "---",
        "",
        "## 5. Firma y Aprobación",
        "",
        "| Rol | Nombre | Firma | Fecha |",
        "|-----|--------|-------|-------|",
        "| Lead V&V Engineer | __________________ | __________________ | __________ |",
        "| QA Manager | __________________ | __________________ | __________ |",
        "| System Engineer | __________________ | __________________ | __________ |",
        "",
        "---",
        "",
        "*Informe generado por `v_and_v_report_generator.py` conforme al proceso de V&V del proyecto.*",
        "",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe V&V generado: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generador de informe formal V&V desde resultado de pytest."
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("pytest_report.json"),
        help="Ruta al reporte JSON de pytest",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("v_and_v_report.md"),
        help="Ruta del archivo Markdown de salida",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("docs/doors_requirements_export.csv"),
        help="Ruta al CSV de requisitos DOORS",
    )
    args = parser.parse_args()

    try:
        pytest_data = load_pytest_report(args.report)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    requirements = load_requirements_csv(args.csv)
    req_to_tests = extract_doors_marks_from_report(pytest_data.get("tests", []))
    generate_markdown_report(pytest_data, req_to_tests, requirements, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
