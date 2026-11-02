# Sistema ATM/C2 – Framework de Automatización de Pruebas V&V (SIL)

> **Rol:** Lead Systems V&V / QA Test Automation Engineer  
> **Dominio:** Sistemas Críticos – Mando y Control (C2) / Air Traffic Management (ATM)  
> **Normativas:** EUROCONTROL ESARR6 · EUROCAE ED-153 · DO-178C · ICAO Annex 11

---

## Descripción del Proyecto

Framework completo de verificación y validación **Software-in-the-Loop (SIL)** para un sistema multicapa compuesto por:

| Nodo | ID | Rol |
|------|----|-----|
| **C2 / ATM Ground Station** | `0x01` | Orquestador central: ingiere telemetría, despacha comandos |
| **Subsistema A – Sensor Radar** | `0x02` | Emite reportes de blanco (azimut, elevación, distancia) |
| **Subsistema B – Servocontrol Antena** | `0x03` | Recibe comandos de posición, confirma con ACK/NACK |

Los tres subsistemas se comunican mediante un **protocolo binario táctico propio** (Big-Endian, SYNC `0xEB90`, checksum de integridad) sobre **sockets UDP** en loopback, sin dependencias de hardware real.

---

## Estructura del Repositorio

```
Proyecto-Militar/
├── docs/
│   ├── doors_requirements_export.csv   # 10 requisitos formales exportados de IBM DOORS
│   └── traceability_matrix.md          # Matriz de trazabilidad cruzada Req ↔ TC
├── tools/
│   ├── doors_traceability_checker.py   # Auditor CLI: cobertura DOORS vs tests
│   └── v_and_v_report_generator.py     # Generador de informe formal V&V (Markdown)
├── simulator/
│   ├── protocol.py                     # Protocolo binario táctico (serialize/deserialize)
│   ├── transport.py                    # Capa UDP sin bloqueo
│   ├── radar_subsystem.py              # Subsistema A: máquina de estados + emisor
│   ├── actuator_subsystem.py           # Subsistema B: servocontrol con ACK/NACK
│   └── c2_mission_system.py            # Sistema Central C2
├── framework/
│   ├── custom_markers.py               # Decorador @doors("REQ-...") para trazabilidad
│   ├── subsystem_client.py             # Cliente de automatización: inyección + polling
│   └── fault_injector.py               # Inyector de fallos: checksum, payload, SYNC, truncación
├── tests/
│   ├── conftest.py                     # Fixtures con puertos dinámicos y teardown garantizado
│   ├── test_subsystem_radar.py         # TC: BVA de rangos, frecuencia, secuencia, estados
│   ├── test_subsystem_actuator.py      # TC: ACK/NACK, posición actualizada, rangos
│   ├── test_end_to_end_system_loop.py  # TC: bucle cerrado completo + integridad coordenadas
│   ├── test_fault_tolerance_robustness.py  # TC: inyección de fallos + subsistema operativo
│   └── test_timing_latency.py          # TC: latencia CMD→ACK, C2 dispatch, E2E RTT
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## Protocolo de Comunicación Binario

### Estructura de Trama

```
┌────────┬────────┬────────┬──────────┬─────────┬─────────────┬─────────┬──────────┐
│ SYNC   │ SRC_ID │ DST_ID │ MSG_TYPE │ SEQ_NUM │ PAYLOAD_LEN │ PAYLOAD │ CHECKSUM │
│  2 B   │  1 B   │  1 B   │   2 B    │   2 B   │    2 B      │ var. B  │   2 B    │
└────────┴────────┴────────┴──────────┴─────────┴─────────────┴─────────┴──────────┘
```

| Campo | Tamaño | Valor |
|-------|--------|-------|
| `SYNC` | 2 B | `0xEB90` (constante de sincronización) |
| `SRC_ID` | 1 B | `0x01`=C2, `0x02`=Radar, `0x03`=Actuador |
| `DST_ID` | 1 B | Idem |
| `MSG_TYPE` | 2 B | `0x0100`=Telemetría, `0x0200`=CMD Posición, `0x0300`=ACK, `0x0301`=NACK |
| `SEQ_NUM` | 2 B | Contador monotónico (wrap en 65535) |
| `PAYLOAD_LEN` | 2 B | Longitud del payload en bytes |
| `PAYLOAD` | var. | Datos tipados según MSG_TYPE |
| `CHECKSUM` | 2 B | Suma de todos los bytes previos mod 65536 |

### Excepciones de Validación

| Excepción | Causa |
|-----------|-------|
| `CorruptSyncError` | SYNC ≠ `0xEB90` |
| `ChecksumMismatchError` | Checksum calculado ≠ embebido |
| `InvalidPayloadLengthError` | `PAYLOAD_LEN` declarado ≠ bytes disponibles |
| `FrameTooShortError` | Buffer < 12 bytes (tamaño mínimo de trama) |

---

## Instalación y Ejecución

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Ejecutar la suite de tests completa

```bash
pytest
```

### 3. Ejecutar con informe HTML

```bash
pytest --html=report.html --self-contained-html
```

### 4. Ejecutar con informe JSON (para el generador V&V)

```bash
pytest --json-report --json-report-file=pytest_report.json
```

### 5. Generar el informe formal V&V

```bash
python tools/v_and_v_report_generator.py \
    --report pytest_report.json \
    --output v_and_v_report.md \
    --csv docs/doors_requirements_export.csv
```

### 6. Auditar cobertura DOORS

```bash
python tools/doors_traceability_checker.py
```

---

## Trazabilidad de Requisitos DOORS

El decorador `@doors("REQ-ID")` (en `framework/custom_markers.py`) vincula cada test con su requisito formal:

```python
from framework.custom_markers import doors

@doors("REQ-ACT-001")
def test_actuator_ack_latency_under_40ms(system):
    """TC-LAT-001: REQ-ACT-001 – ACK en < 40 ms."""
    ...
```

El auditor de trazabilidad verifica la cobertura al 100% y detecta:
- **Requisitos huérfanos**: Req_ID en DOORS sin test asociado.
- **Marcas flotantes**: `@doors` en tests con Req_ID no existente en DOORS.

---

## Suite de Tests – Resumen

| Suite | Nº TCs | Tipo | Requisitos |
|-------|--------|------|-----------|
| `test_subsystem_radar.py` | 15 | BVA + Funcional + Rendimiento | REQ-RADAR-001/002/003/004 |
| `test_subsystem_actuator.py` | 5 | Funcional + Robustez | REQ-ACT-001/002 |
| `test_end_to_end_system_loop.py` | 4 | Integración E2E | REQ-SYS-001/002, REQ-ACT-001, REQ-RADAR-001 |
| `test_fault_tolerance_robustness.py` | 6 | Inyección de Fallos + Estrés | REQ-SYS-ROB-001/002 |
| `test_timing_latency.py` | 4 | Temporización / Latencia | REQ-ACT-001, REQ-SYS-001 |
| **TOTAL** | **34** | | **10 requisitos al 100%** |

---

## Umbrales de Requisitos de Tiempo Real

| Requisito | Umbral | Test |
|-----------|--------|------|
| `REQ-ACT-001` | ACK actuador < **40 ms** | TC-LAT-001, TC-LAT-004 |
| `REQ-SYS-001` | C2 despacha CMD < **50 ms** | TC-LAT-002 |
| `REQ-RADAR-002` | Frecuencia radar ≥ **10 Hz** | TC-RADAR-004 |
| E2E (margen) | Bucle completo < **150 ms** | TC-LAT-003 |

---

## Arquitectura de Inyección de Fallos

```
FaultInjector
├── corrupt_checksum()     → Invierte checksum (CRC inválido)
├── corrupt_payload_len()  → PAYLOAD_LEN = 0xFFFF (overflow)
├── corrupt_sync_word()    → SYNC = 0xDEAD (sync inválido)
├── truncate_frame()       → Trunca a N bytes (< MIN_FRAME_SIZE)
├── should_drop_packet()   → Pérdida probabilística de paquete
└── add_jitter()           → Retardo aleatorio de red
```

---

## Arquitectura de Hilos SIL

```
pytest test runner
    │
    ├── fixture: system (scope=function)
    │       ├── C2MissionSystem         → Thread daemon "C2MissionSystem"
    │       ├── RadarSubsystem          → Thread daemon "RadarSubsystem"
    │       └── ActuatorSubsystem       → Thread daemon "ActuatorSubsystem"
    │
    └── teardown garantizado (stop() + close()) en bloque finally
```

Todos los hilos son **daemon threads**: se terminan automáticamente si el proceso pytest finaliza, garantizando limpieza sin fugas de recursos.

---

## Decisiones de Diseño

| Decisión | Justificación |
|----------|---------------|
| UDP sobre TCP | Refleja el protocolo real de sistemas ATM/radar (DIS, ASTERIX, protocolos tácticos) |
| Puertos dinámicos por fixture | Evita colisiones en ejecuciones paralelas (`pytest-xdist`) |
| Polling con timeout vs `time.sleep()` | Tests deterministas sin esperas ciegas |
| Checksum = suma mod 65536 | Simplicidad y alineación con enfoques de checksum de protocolos tácticos reales |
| Hilos daemon | Teardown automático sin gestión manual de join en cada test |
