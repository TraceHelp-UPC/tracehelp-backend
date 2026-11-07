# Manuales de prueba (T25)

Dos manuales técnicos de **Empresa Demo S.A.C.**, el workspace demo, para validar la ingesta (TS01), la búsqueda de evidencia (T30), la calibración de umbrales (T33) y la demo del sprint. Los procedimientos y códigos de error son reales (Windows, Oracle, Microsoft 365). Los nombres de servidores y del ERP son de la empresa ficticia.

| Archivo | Formato | Contenido | Resultado esperado de la ingesta |
| --- | --- | --- | --- |
| `Manual_Soporte_Tecnico_Empresa_Demo.pdf` | PDF, 6 páginas | VPN (errores 809, 691, 789, 868), ERP Andes (ORA-12541, sesión expirada, roles, FE-2335), carpetas compartidas (0x80070005, versiones anteriores), impresoras (cola, 0x00000709) y escalamiento | VECTORIZED, unos 15 fragmentos, citas con página y párrafo. El encabezado y el número de página repetidos se descartan. |
| `guia-cuentas-correo-colaboracion.md` | Markdown | Contraseñas, cuenta bloqueada, MFA, Outlook, buzón lleno, Teams y OneDrive | VECTORIZED, unos 10 fragmentos, citas con sección y párrafo |

## Cómo cargarlos

1. Inicia sesión en el Dashboard con `lider@demo.tracehelp.pe` y abre **Base de conocimiento** (D-02).
2. Sube el PDF con el título "Manual de soporte técnico" y el Markdown con el título "Guía de cuentas, correo y colaboración".
3. Espera a que los dos lleguen a **VECTORIZED**. Con Gemini tarda menos de un minuto por manual.

## Consultas de validación

Se prueban en `POST /api/v1/triage/evidence-search` con `analista@`. En las de los manuales, el primer fragmento debe tener la cita indicada. En las ajenas al soporte de TI, el resultado debe ser `LOW_CONFIDENCE`. Anota el `best_score` de cada una: es el insumo de T33.

| # | Consulta | Primer fragmento esperado |
| --- | --- | --- |
| 1 | Me sale el error 809 al conectarme a la VPN desde mi casa | PDF, pág. 1 o 2 (2.1 Error 809) |
| 2 | La VPN dice que el usuario o la contraseña no son válidos, error 691 | PDF, pág. 2 (2.2) |
| 3 | Error 789, la capa de seguridad encontró un error de procesamiento L2TP | PDF, pág. 2 (2.3) |
| 4 | El ERP muestra ORA-12541 TNS no listener | PDF, pág. 3 (3.1) |
| 5 | La factura electrónica fue rechazada con el código FE-2335 | PDF, pág. 3 o 4 (3.4) |
| 6 | No puedo abrir la carpeta de Contabilidad en la unidad S, acceso denegado 0x80070005 | PDF, pág. 5 (4.1) |
| 7 | Borré sin querer un archivo de la carpeta compartida, ¿cómo lo recupero? | PDF, pág. 5 (4.3) |
| 8 | Error 0x00000709 al poner la impresora como predeterminada | PDF, pág. 5 o 6 (5.2) |
| 9 | Olvidé mi contraseña del correo | Markdown, sección «Restablecer la contraseña» |
| 10 | Mi cuenta se bloquea sola varias veces al día | Markdown, sección «Cuenta bloqueada» |
| 11 | Cambié de celular y no puedo aprobar el inicio de sesión en Authenticator | Markdown, sección «Verificación en dos pasos (MFA)» |
| 12 | Outlook me pide la contraseña una y otra vez | Markdown, sección «Outlook no se conecta» |
| 13 | No puedo enviar correos porque mi buzón está lleno | Markdown, sección «Buzón lleno» |
| 14 | En las reuniones de Teams no me escuchan | Markdown, sección «Microsoft Teams: audio y cámara» |
| 15 | La silla de mi escritorio rechina | LOW_CONFIDENCE |
| 16 | ¿Cuándo pagan la gratificación de diciembre? | LOW_CONFIDENCE |
| 17 | El aire acondicionado de la sala 3 no enfría | LOW_CONFIDENCE |
| 18 | Quiero solicitar mis vacaciones | LOW_CONFIDENCE |

Si una consulta de los manuales sale con un primer fragmento de otra sección, anótalo también: indica que el texto de esa sección necesita más contexto o que el umbral debe ajustarse en T33.
