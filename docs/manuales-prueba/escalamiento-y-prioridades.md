# Escalamiento y prioridades: severidad CRITICAL, HIGH, MEDIUM y LOW, cuándo escalar a L2 y tiempos de atención

Empresa Demo S.A.C. — Mesa de Ayuda de TI. Versión 1.0, noviembre de 2026.

Este manual indica cómo asignar la severidad a un ticket, cuándo el analista de primer nivel (L1) debe escalar el caso al especialista de segundo nivel (L2) y cuáles son los tiempos de atención de referencia. Úsalo junto con los manuales de cada tema. Primero intenta resolver el caso con el manual correspondiente; escala cuando el problema no se resuelva, cuando afecte a varias personas o cuando el riesgo sea alto.

## Cómo asignar la severidad

La severidad depende del impacto en el trabajo y del riesgo para la información, no de qué tan urgente se sienta el colaborador. Pregunta siempre cuántas personas están afectadas, si el problema impide trabajar por completo y si hay riesgo para datos o cuentas.

Preguntas para decidir:

1. ¿Está afectado un servicio de negocio, como la facturación, el ERP o el correo de toda el área?
2. ¿Cuántas personas no pueden trabajar? Una persona, un área completa o toda la empresa.
3. ¿Hay pérdida de datos, cifrado de archivos o una cuenta comprometida?
4. ¿Existe una alternativa de trabajo? Por ejemplo, otro equipo, otra impresora o acceso desde el celular.
5. ¿El problema se repite o es un hecho aislado?

Si la respuesta a la pregunta 3 es sí, la severidad mínima es HIGH. Si el riesgo afecta a varias áreas, sube a CRITICAL.

## Niveles de severidad

| Severidad | Qué significa | Ejemplos típicos | Tiempo de primera respuesta | Tiempo de solución o plan |
| --- | --- | --- | --- | --- |
| CRITICAL | Servicio de negocio caído o riesgo de seguridad activo que afecta a varias personas | Ransomware en ejecución, ERP caído para toda la empresa, correo caído para todo el personal, servidor de archivos inaccesible, varias cuentas comprometidas | 15 minutos, las 24 horas | 4 horas o plan de contingencia |
| HIGH | Una persona o un grupo no puede trabajar y no hay alternativa, o hay una posible brecha de seguridad | Equipo que no enciende de un colaborador clave, VPN caída para un área, clic en un enlace de phishing con ingreso de contraseña, pantalla azul repetida en un servidor | 1 hora en horario de oficina | 8 horas hábiles |
| MEDIUM | Una persona tiene un problema con alternativa de trabajo o el servicio funciona con fallas | Impresora de red sin imprimir para un área con otra impresora disponible, OneDrive en error de sincronización, licencia de Office sin activar, Teams con caa70004 | 4 horas hábiles | 2 días hábiles |
| LOW | Consulta, configuración o solicitud sin impacto en el trabajo | Cambio de idioma, instalación de un programa del catálogo, solicitud de un periférico adicional, duda de uso | 1 día hábil | 5 días hábiles |

Los tiempos son de referencia para la demo. El analista debe indicar en el ticket el tiempo estimado que propone y confirmarlo con el colaborador.

## Cuándo escalar a L2

Escala a L2 cuando se cumpla al menos una de estas condiciones:

1. Ya seguiste el manual del tema y el problema continúa.
2. El problema afecta a más de una persona de la misma área o del mismo piso.
3. La solución requiere permisos que L1 no tiene, como cambios en servidores, en el firewall o en la configuración de una aplicación de negocio.
4. Hay riesgo para la información o para una cuenta.
5. El código de error no aparece en ningún manual y no se puede resolver con los pasos generales.

Cada escalamiento debe indicar el área de destino. Son cuatro áreas de L2:

### REDES

Atiende los problemas de la red de la empresa: el acceso a internet de un piso, la VPN de sitio, el Wi-Fi corporativo que falla para varios equipos, las direcciones IP que no se asignan, el DNS interno y el proxy.

Escala a REDES cuando:

- Varios equipos del mismo piso tienen 169.254 o pierden internet al mismo tiempo.
- La VPN de computadora no conecta para varias personas, aunque la cuenta esté bien.
- Un cambio de red o de proxy afecta a un área completa.
- La calidad de las reuniones es mala en todas las redes del mismo lugar.

Incluye en el ticket: el lugar afectado, la hora, la salida de `ipconfig /all` de un equipo afectado y los pasos que ya hiciste.

### APLICACIONES

Atiende las aplicaciones de negocio y las de productividad: el ERP, la facturación electrónica, Office, Teams, SharePoint y OneDrive en error persistente, el escritorio remoto cuando la conexión funciona pero la aplicación falla, y la licencia de Office.

Escala a APLICACIONES cuando:

- Una aplicación de negocio no responde o muestra errores de conexión con la base de datos.
- Un documento electrónico fue rechazado con un código de la lista de errores de facturación. Consulta el manual de soporte técnico para los códigos conocidos.
- Los permisos de un sitio de SharePoint deben cambiarse y el dueño no está disponible.
- El error 0x80070643 o 0x8004de40 persiste después de los pasos de L1.

Incluye en el ticket: el nombre de la aplicación, la versión, el código de error completo, el usuario afectado (sin contraseña) y la captura del mensaje.

### INFRAESTRUCTURA

Atiende los servidores, el almacenamiento, los respaldos, la impresión de red, el hardware de los equipos que no puede reparar L1 y las restauraciones de archivos.

Escala a INFRAESTRUCTURA cuando:

- Un equipo muestra un código de parada de hardware, como 0x00000124, o falla de disco repetida.
- Un servidor, un volumen de archivos o una carpeta compartida no está disponible para varias personas.
- Hay que restaurar archivos desde respaldos del servidor.
- Una impresora de red no responde para toda un área, o el docking o el monitor deben reemplazarse.
- La batería de un equipo está desgastada y debe cambiarse.

Incluye en el ticket: el modelo y número de serie del equipo, el código de parada completo, la fecha y hora del último funcionamiento correcto y, en el caso de restauraciones, la ruta y la fecha a la que se quiere volver.

### SEGURIDAD

Atiende los incidentes de seguridad: phishing con ingreso de datos, malware que el antivirus no pudo limpiar, ransomware, cuentas comprometidas, solicitudes de aprobación de MFA que el colaborador no hizo y contraseñas filtradas.

Escala a SEGURIDAD cuando:

- Un colaborador ingresó su contraseña en una página sospechosa.
- El antivirus indica que no pudo limpiar una amenaza.
- Aparecen archivos cifrados o un mensaje de rescate.
- Hay inicios de sesión que la persona no reconoce.
- Un proxy o un DNS fue cambiado sin autorización.

Incluye en el ticket: la hora del incidente, qué hizo la persona antes y después, si el equipo sigue conectado a la red y la captura del mensaje. No incluyas la contraseña ni el contenido completo del correo sospechoso.

## Qué hace L1 antes de escalar

Antes de escalar, el analista L1 debe:

1. Confirmar el problema con el colaborador y registrar el síntoma con las mismas palabras que usó.
2. Aplicar el manual del tema y anotar qué pasos se hicieron y cuál fue el resultado.
3. Asignar la severidad según la tabla de este manual.
4. Asignar el área de L2 que corresponde.
5. Indicar al colaborador qué puede hacer mientras espera, por ejemplo usar otra impresora o trabajar desde el celular con la VPN.

No escales sin registrar la información del ticket. Un ticket sin código de error, sin hora o sin equipo afectado retrasa la atención.

## Cuándo no escalar

No escales si el problema se resuelve con los pasos del manual, si el colaborador no puede confirmar el síntoma después de dos intentos o si la solicitud es de una cuenta que no existe. Tampoco escales las consultas de uso que tienen respuesta en un manual; respóndelas y cierra el ticket con la referencia al manual.

## Cuándo se pasa a CRITICAL de inmediato

Sube la severidad a CRITICAL y avisa al líder de TI cuando:

- Aparezca un mensaje de rescate o archivos cifrados en más de un equipo.
- Un servicio de negocio esté caído para toda la empresa.
- Se confirme el acceso no autorizado a una cuenta con privilegios de administrador.
- Un servidor de archivos o de correo deje de responder.

En esos casos, primero contén el incidente siguiendo el manual de seguridad y después registra el ticket. Un ticket demorado no debe retrasar la contención.

## Cuándo registrar el ticket

Registra el ticket en TraceHelp para cualquier caso que no se resuelva con los manuales. Para incidentes CRITICAL y HIGH de seguridad, también llama a la mesa de ayuda, anexo 4000, para que el analista de guardia reciba la alerta.
