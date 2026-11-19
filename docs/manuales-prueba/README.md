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

## Manuales adicionales para la demo (mesa de ayuda de TI)

Nueve manuales Markdown más, de **Empresa Demo S.A.C.**, para cubrir los incidentes típicos de una mesa de ayuda. Solo tratan temas de TI. Cada archivo empieza con un título H1, una breve descripción de alcance y secciones con el síntoma en palabras del colaborador, los pasos numerados, los códigos de error y cuándo registrar el ticket. Los nombres de servidores, herramientas internas y el anexo de la mesa son ficticios; los procedimientos y los códigos de error (Windows, Microsoft 365, OneDrive, Teams) son reales.

Los archivos no contienen contraseñas, claves, URLs de servicios internos ni datos personales. Todos pesan menos de 10 KB y son Markdown (`.md`), dentro del límite de 25 MB y de los formatos permitidos (`.pdf` y `.md`).

| Archivo | Contenido | Título sugerido en la Base de conocimiento |
| --- | --- | --- |
| `equipos-laptop-pc-no-enciende-lento.md` | Equipo que no enciende, pantalla negra, lentitud, pantalla azul (BSOD) con códigos de parada, batería y sobrecalentamiento | Equipos: no enciende, lentitud y pantalla azul |
| `red-wifi-internet-dns.md` | Wi-Fi sin internet, DNS_PROBE_FINISHED_NO_INTERNET, ERR_NAME_NOT_RESOLVED, IP 169.254, cable de red, portal cautivo y proxy | Red: Wi-Fi sin internet, DNS y cable de red |
| `software-instalacion-licencias-actualizaciones.md` | Instalar y desinstalar programas, error 0x80070643, Windows Update 0x80240034, licencias de Office y permisos de administrador | Software: instalación, licencias y actualizaciones |
| `seguridad-phishing-malware-antivirus.md` | Correo sospechoso y phishing, clic en enlaces peligrosos, alertas del antivirus, ransomware, filtración de contraseña y contraseñas seguras | Seguridad: phishing, malware y antivirus |
| `perifericos-monitores-teclado-mouse-docking.md` | Monitor sin señal, segundo monitor, teclado y mouse, docking, USB no reconocido, audio y webcam | Periféricos: monitores, teclado, mouse, docking y audio |
| `videoconferencia-zoom-teams-meet.md` | Cámara, micrófono, pantalla compartida, inicio de sesión en reuniones, calidad de audio y error caa70004 de Teams | Videoconferencia: Teams, Zoom y Meet |
| `acceso-remoto-escritorio-remoto-vpn-movil.md` | Escritorio remoto (códigos 0x904 y 0x708), VPN en el celular, MFA sin celular y trabajo desde casa | Acceso remoto: escritorio remoto, VPN móvil y MFA |
| `backup-recuperacion-onedrive-sharepoint.md` | OneDrive que no sincroniza, error 0x8004de40, archivos borrados, papelera, historial de versiones, permisos de SharePoint y cuotas | Respaldo: OneDrive, recuperación y SharePoint |
| `escalamiento-y-prioridades.md` | Severidades CRITICAL, HIGH, MEDIUM y LOW, cuándo escalar a L2 (REDES, APLICACIONES, INFRAESTRUCTURA, SEGURIDAD) y tiempos de atención de referencia | Escalamiento y prioridades de TI |

### Cómo subirlos

Se suben desde **Base de conocimiento** (D-02), igual que los dos manuales anteriores: uno por uno, con el título de la columna derecha y el archivo `.md` correspondiente. Espera a que cada uno llegue a **VECTORIZED** antes de subir el siguiente. No se suben en lote, para poder revisar el estado de cada ingesta.

Las consultas de la tabla siguiente son ejemplos para la validación posterior a la carga. Se prueban con `POST /api/v1/triage/evidence-search` como `analista@`. El primer fragmento debe corresponder a la sección indicada. Las consultas no tienen score registrado: anótalo al ejecutarlas, como con los manuales anteriores. No cambies el umbral de 0.68 con estos resultados sin revisarlo en T33.

### Consultas de validación: equipos

| # | Consulta | Primer fragmento esperado |
| --- | --- | --- |
| E1 | Mi laptop no enciende, presiono el botón y no pasa nada | equipos-laptop-pc-no-enciende-lento.md, sección «Mi laptop no enciende o se apaga sola al encender» |
| E2 | Se prende pero la pantalla queda negra, solo veo el cursor | equipos-laptop-pc-no-enciende-lento.md, sección «Pantalla negra: el equipo enciende pero no muestra imagen» |
| E3 | Mi PC va lentísima y tarda minutos en abrir Excel | equipos-laptop-pc-no-enciende-lento.md, sección «Mi PC va muy lenta, se congela o tarda en abrir las aplicaciones» |
| E4 | Me salió la pantalla azul con el código 0x0000007B | equipos-laptop-pc-no-enciende-lento.md, sección «Pantalla azul (BSOD) con código de parada» |
| E5 | Dice que mi PC tuvo un problema y necesita reiniciarse, código 0x00000124 | equipos-laptop-pc-no-enciende-lento.md, sección «Pantalla azul (BSOD) con código de parada» |
| E6 | La batería me dura una hora y no carga aunque esté enchufada | equipos-laptop-pc-no-enciende-lento.md, sección «Mi batería dura muy poco o no carga» |
| E7 | La laptop se calienta mucho y el ventilador suena como aspiradora | equipos-laptop-pc-no-enciende-lento.md, sección «Mi equipo se calienta, hace mucho ruido o se apaga de golpe» |
| E8 | Mi equipo se apaga de golpe cuando trabajo con varias aplicaciones | equipos-laptop-pc-no-enciende-lento.md, sección «Mi equipo se calienta, hace mucho ruido o se apaga de golpe» |

### Consultas de validación: red

| # | Consulta | Primer fragmento esperado |
| --- | --- | --- |
| R1 | Mi Wi-Fi dice conectado pero no abre ninguna página | red-wifi-internet-dns.md, sección «Tengo Wi-Fi pero no tengo internet» |
| R2 | Me aparece DNS_PROBE_FINISHED_NO_INTERNET en el navegador | red-wifi-internet-dns.md, sección «Error DNS_PROBE_FINISHED_NO_INTERNET o ERR_NAME_NOT_RESOLVED» |
| R3 | El navegador dice ERR_NAME_NOT_RESOLVED pero Teams sí funciona | red-wifi-internet-dns.md, sección «Error DNS_PROBE_FINISHED_NO_INTERNET o ERR_NAME_NOT_RESOLVED» |
| R4 | En ipconfig me sale una IP 169.254 y no tengo red | red-wifi-internet-dns.md, sección «IP que empieza por 169.254 (sin acceso a la red)» |
| R5 | Tengo el cable de red conectado pero la luz del puerto no prende | red-wifi-internet-dns.md, sección «Cable de red (Ethernet) sin conexión» |
| R6 | En el Wi-Fi de visitantes no me abre la página para iniciar sesión | red-wifi-internet-dns.md, sección «Portal cautivo: la red pide iniciar sesión en el navegador» |
| R7 | Solo abren algunas páginas y sale ERR_PROXY_CONNECTION_FAILED | red-wifi-internet-dns.md, sección «Configuración de proxy que bloquea las páginas» |
| R8 | Se cayó internet a varios compañeros de mi piso al mismo tiempo | red-wifi-internet-dns.md, sección «Tengo Wi-Fi pero no tengo internet» |

### Consultas de validación: software

| # | Consulta | Primer fragmento esperado |
| --- | --- | --- |
| S1 | Necesito instalar un programa que no aparece en la lista | software-instalacion-licencias-actualizaciones.md, sección «Quiero instalar un programa» |
| S2 | No me deja desinstalar un programa, el botón Desinstalar sale gris | software-instalacion-licencias-actualizaciones.md, sección «Quiero desinstalar un programa» |
| S3 | La instalación se detuvo con el código 0x80070643 | software-instalacion-licencias-actualizaciones.md, sección «Error 0x80070643 al instalar o actualizar un programa» |
| S4 | Windows Update muestra el error 0x80240034 y no descarga nada | software-instalacion-licencias-actualizaciones.md, sección «Windows Update no descarga actualizaciones: error 0x80240034» |
| S5 | Office dice que este producto no tiene licencia | software-instalacion-licencias-actualizaciones.md, sección «Licencia de Office no válida o producto sin activar» |
| S6 | Al activar Office me sale el código 0xC004F074 | software-instalacion-licencias-actualizaciones.md, sección «Licencia de Office no válida o producto sin activar» |
| S7 | Me pide la contraseña de administrador para instalar algo | software-instalacion-licencias-actualizaciones.md, sección «Necesito permisos de administrador para instalar o cambiar algo» |
| S8 | Excel se cierra sola después de la última actualización | software-instalacion-licencias-actualizaciones.md, sección «Mi programa de Office no abre o se cierra al iniciar» |

### Consultas de validación: seguridad

| # | Consulta | Primer fragmento esperado |
| --- | --- | --- |
| SE1 | Me llegó un correo del banco que me pide la clave con urgencia | seguridad-phishing-malware-antivirus.md, sección «Recibí un correo sospechoso o de phishing» |
| SE2 | Hice clic en un enlace raro y me pidió mi contraseña | seguridad-phishing-malware-antivirus.md, sección «Hice clic en un enlace o abrí un adjunto sospechoso» |
| SE3 | Me salió una alerta de amenaza de Seguridad de Windows | seguridad-phishing-malware-antivirus.md, sección «Alerta del antivirus o de Microsoft Defender» |
| SE4 | Mis archivos tienen otra extensión y un mensaje pide pagar para recuperarlos | seguridad-phishing-malware-antivirus.md, sección «Mis archivos aparecen cifrados o con otra extensión (ransomware)» |
| SE5 | Recibí un aviso de que mi contraseña apareció en una filtración | seguridad-phishing-malware-antivirus.md, sección «Creo que mi contraseña se filtró» |
| SE6 | ¿Cómo hago una contraseña segura para mi correo? | seguridad-phishing-malware-antivirus.md, sección «Cómo crear una contraseña segura» |
| SE7 | Alguien inició sesión en mi cuenta desde otro país | seguridad-phishing-malware-antivirus.md, sección «Creo que mi contraseña se filtró» |
| SE8 | ¿Cuándo debo reportar un incidente de seguridad? | seguridad-phishing-malware-antivirus.md, sección «Cuándo registrar un incidente de seguridad» |

### Consultas de validación: periféricos

| # | Consulta | Primer fragmento esperado |
| --- | --- | --- |
| P1 | El monitor se prende pero dice Sin señal | perifericos-monitores-teclado-mouse-docking.md, sección «El monitor dice "Sin señal"» |
| P2 | Quiero usar dos pantallas y el segundo monitor no aparece | perifericos-monitores-teclado-mouse-docking.md, sección «Quiero usar un segundo monitor o extender la pantalla» |
| P3 | El teclado inalámbrico ya no escribe y el mouse se mueve a saltos | perifericos-monitores-teclado-mouse-docking.md, sección «Teclado o mouse que no responden» |
| P4 | Al conectar la laptop al docking no pasa nada | perifericos-monitores-teclado-mouse-docking.md, sección «Estación de acoplamiento (docking) que no funciona» |
| P5 | Conecto la memoria USB y dice Dispositivo USB no reconocido, código 43 | perifericos-monitores-teclado-mouse-docking.md, sección «Un USB no es reconocido o aparece "Dispositivo USB no reconocido"» |
| P6 | No sale sonido de mis audífonos y dice que no hay dispositivos de salida de audio | perifericos-monitores-teclado-mouse-docking.md, sección «Audio: no suena, el micrófono no funciona o aparece "No hay dispositivos de salida de audio instalados"» |
| P7 | La webcam sale negra cuando entro a la reunión | perifericos-monitores-teclado-mouse-docking.md, sección «Webcam que no aparece o sale en negro» |
| P8 | Mi micrófono no capta mi voz en la laptop | perifericos-monitores-teclado-mouse-docking.md, sección «Audio: no suena, el micrófono no funciona o aparece "No hay dispositivos de salida de audio instalados"» |

### Consultas de validación: videoconferencia

| # | Consulta | Primer fragmento esperado |
| --- | --- | --- |
| V1 | En la reunión de Teams no me escuchan | videoconferencia-zoom-teams-meet.md, sección «No me escuchan en la reunión o no escucho a los demás» |
| V2 | Hay eco y mi voz se corta en la videollamada | videoconferencia-zoom-teams-meet.md, sección «No me escuchan en la reunión o no escucho a los demás» |
| V3 | La cámara sale negra y dice que está en uso | videoconferencia-zoom-teams-meet.md, sección «La cámara aparece en negro o no aparece» |
| V4 | Teams muestra el código caa70004 al unirme | videoconferencia-zoom-teams-meet.md, sección «Error caa70004 en Microsoft Teams» |
| V5 | Cuando comparto pantalla, los demás ven todo negro | videoconferencia-zoom-teams-meet.md, sección «Pantalla compartida: no se ve, sale en negro o el público ve otra ventana» |
| V6 | No me deja iniciar sesión en la reunión y me pide la contraseña una y otra vez | videoconferencia-zoom-teams-meet.md, sección «No puedo iniciar sesión en la reunión o en la aplicación» |
| V7 | La video llamada se congela y se ve pixelada | videoconferencia-zoom-teams-meet.md, sección «Mala calidad de video o audio entrecortado» |
| V8 | Un cliente me pidió una reunión por Zoom, ¿qué debo usar? | videoconferencia-zoom-teams-meet.md, sección «Google Meet o Zoom en reuniones con clientes» |

### Consultas de validación: acceso remoto

| # | Consulta | Primer fragmento esperado |
| --- | --- | --- |
| A1 | Me sale el error 0x904 al conectarme al escritorio remoto de la oficina | acceso-remoto-escritorio-remoto-vpn-movil.md, sección «Escritorio remoto: no me conecta a mi equipo de la oficina» |
| A2 | Desde casa aparece el código 0x708 y no entro al escritorio remoto | acceso-remoto-escritorio-remoto-vpn-movil.md, sección «Escritorio remoto: no me conecta a mi equipo de la oficina» |
| A3 | Mi usuario no tiene permiso para el escritorio remoto | acceso-remoto-escritorio-remoto-vpn-movil.md, sección «Mi usuario no tiene permiso para el escritorio remoto» |
| A4 | Necesito la VPN en mi celular, ¿cómo la instalo? | acceso-remoto-escritorio-remoto-vpn-movil.md, sección «VPN en el celular: quiero entrar a los sistemas desde el teléfono» |
| A5 | La VPN del celular se desconecta cada pocos minutos | acceso-remoto-escritorio-remoto-vpn-movil.md, sección «VPN en el celular: quiero entrar a los sistemas desde el teléfono» |
| A6 | No me llega la notificación de Authenticator cuando estoy fuera de la oficina | acceso-remoto-escritorio-remoto-vpn-movil.md, sección «Verificación en dos pasos (MFA): no me llega la aprobación fuera de la oficina» |
| A7 | Cambié de celular y no puedo aprobar el inicio de sesión | acceso-remoto-escritorio-remoto-vpn-movil.md, sección «Verificación en dos pasos (MFA): no me llega la aprobación fuera de la oficina» |
| A8 | ¿Qué necesito para trabajar desde casa con mi equipo de la empresa? | acceso-remoto-escritorio-remoto-vpn-movil.md, sección «Trabajo desde casa: qué debo tener y cómo conectarme» |

### Consultas de validación: respaldo y recuperación

| # | Consulta | Primer fragmento esperado |
| --- | --- | --- |
| B1 | OneDrive tiene una cruz roja y no sincroniza mis archivos | backup-recuperacion-onedrive-sharepoint.md, sección «OneDrive no sincroniza mis archivos» |
| B2 | OneDrive muestra el error 0x8004de40 al iniciar sesión | backup-recuperacion-onedrive-sharepoint.md, sección «OneDrive muestra el error 0x8004de40 al iniciar sesión» |
| B3 | Borré sin querer un archivo de la carpeta compartida, ¿cómo lo recupero? | backup-recuperacion-onedrive-sharepoint.md, sección «Quiero recuperar un archivo que borré» |
| B4 | ¿Cuánto tiempo se guardan los archivos borrados en la papelera de OneDrive? | backup-recuperacion-onedrive-sharepoint.md, sección «Quiero recuperar un archivo que borré» |
| B5 | Necesito volver a la versión de ayer de un documento | backup-recuperacion-onedrive-sharepoint.md, sección «Quiero recuperar un archivo que borré» |
| B6 | Guardé mis documentos en el escritorio y no salen en OneDrive | backup-recuperacion-onedrive-sharepoint.md, sección «Archivos de mi equipo que no están en la nube» |
| B7 | No puedo abrir el sitio de SharePoint del proyecto, me dice que no tengo acceso | backup-recuperacion-onedrive-sharepoint.md, sección «Permisos de SharePoint: no puedo abrir el sitio o el archivo» |
| B8 | OneDrive dice que no hay espacio suficiente para subir archivos | backup-recuperacion-onedrive-sharepoint.md, sección «Mi cuenta de OneDrive o SharePoint no tiene espacio» |

### Consultas de validación: escalamiento y prioridades

| # | Consulta | Primer fragmento esperado |
| --- | --- | --- |
| X1 | ¿Cómo sé si un ticket es CRITICAL o HIGH? | escalamiento-y-prioridades.md, sección «Cómo asignar la severidad» |
| X2 | ¿Cuál es el tiempo de primera respuesta para una severidad MEDIUM? | escalamiento-y-prioridades.md, sección «Niveles de severidad» |
| X3 | Varios equipos del piso perdieron la IP y no tienen red, ¿cuándo escalo a L2? | escalamiento-y-prioridades.md, sección «REDES» |
| X4 | Un correo de phishing pidió credenciales a un colaborador, ¿a qué área escalo? | escalamiento-y-prioridades.md, sección «SEGURIDAD» |
| X5 | Un servidor de archivos no responde para toda un área, ¿qué severidad le doy? | escalamiento-y-prioridades.md, sección «Niveles de severidad» |
| X6 | ¿Qué información debo incluir al escalar un problema de servidores o hardware? | escalamiento-y-prioridades.md, sección «INFRAESTRUCTURA» |
| X7 | Un error de factura electrónica rechazada, ¿a qué área de L2 va? | escalamiento-y-prioridades.md, sección «APLICACIONES» |
| X8 | ¿Qué debe hacer el analista de primer nivel antes de escalar? | escalamiento-y-prioridades.md, sección «Qué hace L1 antes de escalar» |

Las consultas #15 a #18 de la calibración siguen siendo fuera de dominio y deben seguir devolviendo `LOW_CONFIDENCE`. Revisa que los manuales nuevos no las alteren antes de dar por cerrada la carga.
