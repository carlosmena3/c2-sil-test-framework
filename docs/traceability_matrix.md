# Matriz de Trazabilidad V&V — Sistema ATM / Mando y Control

> **Normativas aplicables:** EUROCONTROL ESARR6 · EUROCAE ED-153 · DO-178C · ICAO Annex 11  
> **Generado:** 2026-10-31  
> **Versión del baseline de requisitos:** 1.0

---

## 1. Tabla de Trazabilidad Cruzada: Requisitos ↔ Casos de Prueba

| Req_ID | Descripción (resumen) | Safety | Sistema | Caso(s) de Prueba | Suite |
|--------|----------------------|--------|---------|-------------------|-------|
| `REQ-RADAR-001` | Azimut ∈ [0°, 360°) y Elevación ∈ [-90°, 90°] | DAL-B | RADAR | TC-RADAR-001a/b/c/d, TC-RADAR-002a/b/c/d, TC-RADAR-006 | `test_subsystem_radar.py` |
| `REQ-RADAR-002` | Frecuencia actualización ≥ 10 Hz | DAL-B | RADAR | TC-RADAR-004 | `test_subsystem_radar.py` |
| `REQ-RADAR-003` | Distancia ∈ [0, 500] NM | DAL-C | RADAR | TC-RADAR-003a/b/c/d | `test_subsystem_radar.py` |
| `REQ-RADAR-004` | Secuencia monotónicamente creciente | DAL-C | RADAR | TC-RADAR-005 | `test_subsystem_radar.py` |
| `REQ-ACT-001` | ACK de posición en < 40 ms | DAL-A | ACTUATOR | TC-ACT-001/002/005, TC-LAT-001/003/004 | `test_subsystem_actuator.py`, `test_timing_latency.py` |
| `REQ-ACT-002` | NACK para rango de posición inválido | DAL-A | ACTUATOR | TC-ACT-003/004 | `test_subsystem_actuator.py` |
| `REQ-SYS-001` | C2 despacha CMD en < 50 ms tras telemetría | DAL-A | C2 | TC-E2E-001/003, TC-LAT-002/003 | `test_end_to_end_system_loop.py`, `test_timing_latency.py` |
| `REQ-SYS-002` | C2 actualiza última posición de blanco | DAL-B | C2 | TC-E2E-001/002/004 | `test_end_to_end_system_loop.py` |
| `REQ-SYS-ROB-001` | Descartar checksum inválido → NACK + operativo | DAL-A | ALL | TC-ROB-001/003/005/006 | `test_fault_tolerance_robustness.py` |
| `REQ-SYS-ROB-002` | Descartar PAYLOAD_LEN inconsistente → operativo | DAL-A | ALL | TC-ROB-002/004/006 | `test_fault_tolerance_robustness.py` |

---

## 2. Índice de Casos de Prueba

| TC_ID | Nombre del Test | Suite | Req_ID(s) | Tipo |
|-------|-----------------|-------|-----------|------|
| TC-RADAR-001a | `test_valid_azimuth_boundary_min` | radar | REQ-RADAR-001 | BVA |
| TC-RADAR-001b | `test_valid_azimuth_boundary_max` | radar | REQ-RADAR-001 | BVA |
| TC-RADAR-001c | `test_invalid_azimuth_negative` | radar | REQ-RADAR-001 | BVA |
| TC-RADAR-001d | `test_invalid_azimuth_360` | radar | REQ-RADAR-001 | BVA |
| TC-RADAR-002a | `test_valid_elevation_min` | radar | REQ-RADAR-001 | BVA |
| TC-RADAR-002b | `test_valid_elevation_max` | radar | REQ-RADAR-001 | BVA |
| TC-RADAR-002c | `test_invalid_elevation_below_min` | radar | REQ-RADAR-001 | BVA |
| TC-RADAR-002d | `test_invalid_elevation_above_max` | radar | REQ-RADAR-001 | BVA |
| TC-RADAR-003a | `test_valid_distance_zero` | radar | REQ-RADAR-003 | BVA |
| TC-RADAR-003b | `test_valid_distance_max` | radar | REQ-RADAR-003 | BVA |
| TC-RADAR-003c | `test_invalid_distance_negative` | radar | REQ-RADAR-003 | BVA |
| TC-RADAR-003d | `test_invalid_distance_over_max` | radar | REQ-RADAR-003 | BVA |
| TC-RADAR-004 | `test_radar_update_frequency` | radar | REQ-RADAR-002 | Rendimiento |
| TC-RADAR-005 | `test_radar_sequence_numbers_monotonic` | radar | REQ-RADAR-004 | Funcional |
| TC-RADAR-006 | `test_radar_state_transitions` | radar | REQ-RADAR-001 | Máquina estados |
| TC-ACT-001 | `test_actuator_ack_on_valid_command` | actuator | REQ-ACT-001 | Funcional |
| TC-ACT-002 | `test_actuator_position_updated_after_command` | actuator | REQ-ACT-001 | Funcional |
| TC-ACT-003 | `test_actuator_nack_on_invalid_azimuth` | actuator | REQ-ACT-002 | Funcional |
| TC-ACT-004 | `test_actuator_nack_on_invalid_elevation` | actuator | REQ-ACT-002 | Funcional |
| TC-ACT-005 | `test_actuator_returns_to_ready_after_move` | actuator | REQ-ACT-001 | Máquina estados |
| TC-E2E-001 | `test_full_closed_loop` | e2e | REQ-SYS-001/002, REQ-ACT-001, REQ-RADAR-001 | Integración |
| TC-E2E-002 | `test_c2_updates_track_on_each_telemetry` | e2e | REQ-SYS-002 | Funcional |
| TC-E2E-003 | `test_coordinate_integrity_through_chain` | e2e | REQ-SYS-001, REQ-RADAR-001 | Integridad datos |
| TC-E2E-004 | `test_no_command_without_target` | e2e | REQ-SYS-002 | Negativo |
| TC-ROB-001 | `test_corrupt_checksum_actuator_sends_nack` | robustness | REQ-SYS-ROB-001 | Inyección fallos |
| TC-ROB-002 | `test_corrupt_payload_len_actuator_sends_nack` | robustness | REQ-SYS-ROB-002 | Inyección fallos |
| TC-ROB-003 | `test_corrupt_sync_word_no_crash` | robustness | REQ-SYS-ROB-001 | Inyección fallos |
| TC-ROB-004 | `test_truncated_frame_no_crash` | robustness | REQ-SYS-ROB-002 | Inyección fallos |
| TC-ROB-005 | `test_c2_discards_corrupt_telemetry` | robustness | REQ-SYS-ROB-001 | Inyección fallos |
| TC-ROB-006 | `test_sustained_fault_injection_system_remains_operational` | robustness | REQ-SYS-ROB-001/002 | Estrés |
| TC-LAT-001 | `test_actuator_ack_latency_under_40ms` | latency | REQ-ACT-001 | Temporización |
| TC-LAT-002 | `test_c2_dispatch_latency_under_50ms` | latency | REQ-SYS-001 | Temporización |
| TC-LAT-003 | `test_end_to_end_loop_latency` | latency | REQ-SYS-001, REQ-ACT-001 | Temporización E2E |
| TC-LAT-004 | `test_actuator_latency_stability` | latency | REQ-ACT-001 | Estabilidad temporal |

---

## 3. Métricas de Cobertura

| Métrica | Valor |
|---------|-------|
| Total requisitos en baseline | 10 |
| Requisitos con test asociado | 10 |
| **Cobertura de requisitos** | **100%** |
| Total casos de prueba | 34 |
| Requisitos DAL-A cubiertos | 4/4 (100%) |
| Requisitos DAL-B cubiertos | 3/3 (100%) |
| Requisitos DAL-C cubiertos | 2/2 (100%) |

---

## 4. Tipos de Prueba por Categoría

| Categoría | Cantidad | % del total |
|-----------|----------|-------------|
| Análisis de Valores Límite (BVA) | 12 | 35% |
| Funcional | 8 | 24% |
| Inyección de Fallos | 6 | 18% |
| Temporización / Latencia | 4 | 12% |
| Integración E2E | 4 | 12% |
