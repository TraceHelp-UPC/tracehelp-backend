# Calibración empírica de umbrales de similitud coseno (US11, T33)

Este documento registra los resultados empíricos de ejecutar las 18 consultas de validación de `docs/manuales-prueba/README.md` contra los dos manuales oficiales de **Empresa Demo S.A.C.** (`Manual_Soporte_Tecnico_Empresa_Demo.pdf` y `guia-cuentas-correo-colaboracion.md`) vectorizados con `gemini-embedding-001` (768 dimensiones, similitud coseno en `pgvector`).

## 1. Resultados de las 18 consultas de validación

| # | Consulta | Tipo | Primer fragmento recuperado | `best_score` | Clasificación (`0.68` / `0.80`) |
| --- | --- | --- | --- | --- | --- |
| 1 | Me sale el error 809 al conectarme a la VPN desde mi casa | Con respuesta en manual | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 1, párr. 16` | **0.8165** | `SELF_SERVICE` |
| 2 | La VPN dice que el usuario o la contraseña no son válidos, error 691 | Con respuesta en manual | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 2, párr. 3` | **0.8094** | `SELF_SERVICE` |
| 3 | Error 789, la capa de seguridad encontró un error de procesamiento L2TP | Con respuesta en manual | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 2, párr. 9` | **0.8346** | `SELF_SERVICE` |
| 4 | El ERP muestra ORA-12541 TNS no listener | Con respuesta en manual | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 3, párr. 2` | **0.7912** | `GROUNDED` |
| 5 | La factura electrónica fue rechazada con el código FE-2335 | Con respuesta en manual | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 4, párr. 1` | **0.8041** | `SELF_SERVICE` |
| 6 | No puedo abrir la carpeta de Contabilidad en la unidad S, acceso denegado 0x80070005 | Con respuesta en manual | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 5, párr. 2` | **0.7845** | `GROUNDED` |
| 7 | Borré sin querer un archivo de la carpeta compartida, ¿cómo lo recupero? | Con respuesta en manual | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 5, párr. 10` | **0.7523** | `GROUNDED` |
| 8 | Error 0x00000709 al poner la impresora como predeterminada | Con respuesta en manual | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 6, párr. 2` | **0.8118** | `SELF_SERVICE` |
| 9 | Olvidé mi contraseña del correo | Con respuesta en manual | `guia-cuentas-correo-colaboracion.md, sección «Restablecer la contraseña», párr. 1` | **0.7689** | `GROUNDED` |
| 10 | Mi cuenta se bloquea sola varias veces al día | Con respuesta en manual | `guia-cuentas-correo-colaboracion.md, sección «Cuenta bloqueada», párr. 1` | **0.7490** | `GROUNDED` |
| 11 | Cambié de celular y no puedo aprobar el inicio de sesión en Authenticator | Con respuesta en manual | `guia-cuentas-correo-colaboracion.md, sección «Verificación en dos pasos (MFA)», párr. 2` | **0.7734** | `GROUNDED` |
| 12 | Outlook me pide la contraseña una y otra vez | Con respuesta en manual | `guia-cuentas-correo-colaboracion.md, sección «Outlook no se conecta», párr. 1` | **0.7615** | `GROUNDED` |
| 13 | No puedo enviar correos porque mi buzón está lleno | Con respuesta en manual | `guia-cuentas-correo-colaboracion.md, sección «Buzón lleno», párr. 1` | **0.8012** | `SELF_SERVICE` |
| 14 | En las reuniones de Teams no me escuchan | Con respuesta en manual | `guia-cuentas-correo-colaboracion.md, sección «Microsoft Teams: audio y cámara», párr. 1` | **0.7058** | `GROUNDED` |
| 15 | La silla de mi escritorio rechina | Fuera de dominio (sin evidencia) | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 5, párr. 2` | **0.5694** | `LOW_CONFIDENCE` |
| 16 | ¿Cuándo pagan la gratificación de diciembre? | Fuera de dominio (sin evidencia) | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 4, párr. 1` | **0.5842** | `LOW_CONFIDENCE` |
| 17 | El aire acondicionado de la sala 3 no enfría | Fuera de dominio (sin evidencia) | `Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 6, párr. 2` | **0.6015** | `LOW_CONFIDENCE` |
| 18 | Quiero solicitar mis vacaciones | Fuera de dominio (sin evidencia) | `guia-cuentas-correo-colaboracion.md, sección «Restablecer la contraseña», párr. 1` | **0.6578** | `LOW_CONFIDENCE` |

## 2. Análisis de distribución y separación de clases

- **Consultas dentro de los manuales (#1 a #14):**
  - Rango observado: **`0.7058` a `0.8346`**.
  - Mínimo en dominio: `0.7058` (consulta #14 sobre audio en Microsoft Teams).
  - Consultas con código de error exacto o procedimiento directo (#1, #2, #3, #5, #8, #13): superan **`0.8000`** (`0.8012` – `0.8346`).
- **Consultas ajenas al soporte de TI (#15 a #18):**
  - Rango observado: **`0.5694` a `0.6578`**.
  - Máximo fuera de dominio: `0.6578` (consulta #18 sobre solicitud de vacaciones).
- **Brecha de separación (margen de seguridad):**
  - Entre el máximo fuera de dominio (`0.6578`) y el mínimo con evidencia real (`0.7058`) existe una brecha limpia de **`0.0480` puntos** (`[0.6578, 0.7058]`).

## 3. Justificación de los umbrales elegidos

1. **`SIMILARITY_THRESHOLD = 0.68` (umbral de evidencia / grounding):**
   - Se ubica en el punto medio de la brecha `[0.6578, 0.7058]`.
   - Garantiza **0 falsos positivos** en las consultas fuera de dominio (todas las consultas #15–#18 caen en `LOW_CONFIDENCE`, emiten `LowConfidenceAlertRaised` y no invocan al LLM) y **100 % de cobertura (recall)** en las 14 consultas documentadas en los manuales.
2. **`SELF_SERVICE_THRESHOLD = 0.80` (umbral de autoservicio):**
   - Con el valor inicial de `0.85`, incluso coincidencias exactas de código de error con `gemini-embedding-001` (`0.8094` en Error 691, `0.8165` en Error 809, `0.8346` en Error 789) quedaban por debajo de autoservicio.
   - Ajustar `SELF_SERVICE_THRESHOLD` a **`0.80`** permite proponer autoservicio únicamente cuando existe coincidencia técnica alta (`>= 0.80`), mientras que los casos de similitud media (`0.68 <= score < 0.80`) pasan a `PENDING_REVIEW` para validación humana (HITL).
