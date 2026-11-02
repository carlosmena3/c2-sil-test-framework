#!/usr/bin/env python3
"""Auditor de cobertura de requisitos DOORS vs suite de tests."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import NamedTuple


class Requirement(NamedTuple):
    req_id: str
    object_text: str
    allocated_system: str
    verification_method: str
    safety_level: str


class TraceabilityReport(NamedTuple):
    covered_reqs: set[str]
    orphan_reqs: set[str]
    unknown_marks: set[str]
    req_to_tests: dict[str, list[str]]


DOORS_DECORATOR_PATTERN: re.Pattern[str] = re.compile(
    r'@doors\(\s*["\'](?P<req_id>REQ-[A-Z0-9_\-]+)["\']'
    r'|@pytest\.mark\.doors\(\s*req_id\s*=\s*["\'](?P<req_id2>REQ-[A-Z0-9_\-]+)["\']'
)


def load_requirements(csv_path: Path) -> dict[str, Requirement]:
    """Carga los requisitos desde el CSV exportado de DOORS."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV de DOORS no encontrado: {csv_path}")

    requirements: dict[str, Requirement] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        expected_fields = {
            "Req_ID",
            "Object_Text",
            "Allocated_System",
            "Verification_Method",
            "Safety_Level",
        }
        if not expected_fields.issubset(set(reader.fieldnames or [])):
            raise ValueError(
                f"El CSV no contiene las columnas esperadas: {expected_fields}"
            )
        for row in reader:
            req_id = row["Req_ID"].strip()
            if req_id:
                requirements[req_id] = Requirement(
                    req_id=req_id,
                    object_text=row["Object_Text"].strip(),
                    allocated_system=row["Allocated_System"].strip(),
                    verification_method=row["Verification_Method"].strip(),
                    safety_level=row["Safety_Level"].strip(),
                )
    return requirements


def extract_doors_marks(tests_dir: Path) -> dict[str, list[str]]:
    """Extrae las referencias @doors de los archivos test_*.py."""
    marks: dict[str, list[str]] = {}
    test_files = sorted(tests_dir.glob("test_*.py"))

    for test_file in test_files:
        content = test_file.read_text(encoding="utf-8")
        for match in DOORS_DECORATOR_PATTERN.finditer(content):
            req_id = match.group("req_id") or match.group("req_id2")
            if req_id:
                marks.setdefault(req_id, []).append(test_file.name)

    return marks


def audit_traceability(
    requirements: dict[str, Requirement],
    marks: dict[str, list[str]],
) -> TraceabilityReport:
    """Cruza los requisitos del CSV con las marcas encontradas en los tests."""
    all_req_ids: set[str] = set(requirements.keys())
    marked_req_ids: set[str] = set(marks.keys())

    covered_reqs: set[str] = all_req_ids & marked_req_ids
    orphan_reqs: set[str] = all_req_ids - marked_req_ids
    unknown_marks: set[str] = marked_req_ids - all_req_ids

    return TraceabilityReport(
        covered_reqs=covered_reqs,
        orphan_reqs=orphan_reqs,
        unknown_marks=unknown_marks,
        req_to_tests=marks,
    )


def print_report(
    requirements: dict[str, Requirement],
    report: TraceabilityReport,
) -> None:
    """Imprime el informe de trazabilidad en consola."""
    total = len(requirements)
    covered = len(report.covered_reqs)
    coverage_pct = (covered / total * 100) if total > 0 else 0.0

    separator = "=" * 70
    print(f"\n{separator}")
    print("  DOORS TRACEABILITY COVERAGE REPORT")
    print(separator)
    print(f"  Total requisitos DOORS : {total}")
    print(f"  Requisitos cubiertos   : {covered}")
    print(f"  Cobertura              : {coverage_pct:.1f}%")
    print(separator)

    if report.covered_reqs:
        print("\n  [OK] REQUISITOS CUBIERTOS:")
        for req_id in sorted(report.covered_reqs):
            tests = report.req_to_tests.get(req_id, [])
            safety = requirements[req_id].safety_level
            print(f"     [{safety}] {req_id} -> {', '.join(sorted(set(tests)))}")

    if report.orphan_reqs:
        print("\n  [FAIL] REQUISITOS HUERFANOS (sin test asociado):")
        for req_id in sorted(report.orphan_reqs):
            safety = requirements[req_id].safety_level
            obj = requirements[req_id].object_text[:60]
            print(f"     [{safety}] {req_id} -- {obj}...")

    if report.unknown_marks:
        print("\n  [WARN] MARCAS EN TESTS SIN REQUISITO EN DOORS:")
        for req_id in sorted(report.unknown_marks):
            tests = report.req_to_tests.get(req_id, [])
            print(f"     {req_id} -> encontrado en: {', '.join(sorted(set(tests)))}")

    print(f"\n{separator}\n")


def main() -> int:
    """Punto de entrada. Retorna 0 si cobertura es 100%, 1 en caso contrario."""
    parser = argparse.ArgumentParser(
        description="Auditor de trazabilidad DOORS vs tests de automatización."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("docs/doors_requirements_export.csv"),
        help="Ruta al CSV de exportación DOORS",
    )
    parser.add_argument(
        "--tests",
        type=Path,
        default=Path("tests"),
        help="Directorio de tests a escanear",
    )
    args = parser.parse_args()

    try:
        requirements = load_requirements(args.csv)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR cargando requisitos DOORS: {exc}", file=sys.stderr)
        return 1

    marks = extract_doors_marks(args.tests)
    report = audit_traceability(requirements, marks)
    print_report(requirements, report)

    if report.orphan_reqs:
        print(
            f"  FALLO: {len(report.orphan_reqs)} requisito(s) sin cobertura de test.",
            file=sys.stderr,
        )
        return 1

    if report.unknown_marks:
        print(
            f"  ADVERTENCIA: {len(report.unknown_marks)} marca(s) en tests "
            "sin correspondencia en DOORS.",
            file=sys.stderr,
        )

    print("  [OK] Cobertura DOORS: 100%. Todos los requisitos tienen test asociado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
