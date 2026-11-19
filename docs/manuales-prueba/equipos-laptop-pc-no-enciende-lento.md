# Equipos: la laptop o la PC no enciende, va lenta o muestra pantalla azul

Empresa Demo S.A.C. — Mesa de Ayuda de TI. Versión 1.0, noviembre de 2026.

Este manual resuelve en primer nivel los problemas más frecuentes de las laptops y PC de la empresa: el equipo no enciende, la pantalla queda negra, va muy lento, muestra una pantalla azul con un código de parada, la batería dura poco o el equipo se calienta. Sigue los pasos en orden y no saltes ninguno. Si el problema continúa, registra el ticket y adjunta el código de error o una foto de la pantalla azul.

## Mi laptop no enciende o se apaga sola al encender

Síntomas habituales: "no prende", "presiono el botón y no pasa nada", "la laptop no da señal", "se apaga sola cuando ya casi carga".

1. Revisa que el cargador esté conectado firmemente al equipo y al tomacorriente. Prueba con otro tomacorriente.
2. Observa si se enciende la luz indicadora del cargador o la luz de energía del equipo. Si no se enciende ninguna luz, el problema puede ser el cargador o la batería.
3. Mantén presionado el botón de encendido durante 15 segundos para forzar el apagado. Espera 30 segundos y vuelve a encender el equipo.
4. Si el equipo enciende y se apaga en menos de un minuto, desconecta todos los periféricos (USB, docking, monitor externo, impresora) y vuelve a encenderlo.
5. Si aparece el mensaje "Preparando la reparación automática" y se repite, selecciona Opciones avanzadas, luego Solución de problemas, Opciones avanzadas y Símbolo del sistema. Escribe `chkdsk C: /f` y presiona Enter. Reinicia el equipo cuando termine.
6. Si no enciende nada (ni luz, ni ventilador, ni pantalla), registra un ticket con el modelo y el número de serie del equipo. Esto pasa a INFRAESTRUCTURA como fallo de hardware.

## Pantalla negra: el equipo enciende pero no muestra imagen

Síntomas habituales: "se prende pero la pantalla queda negra", "veo el logo y después se pone negra", "solo se ve el cursor en negro", "la pantalla parpadea y se apaga".

1. Espera un minuto. Algunos equipos tardan en mostrar la imagen después de un inicio de sesión o una actualización.
2. Presiona Windows + Ctrl + Shift + B. El equipo reinicia solo el controlador gráfico y, si funciona, la pantalla vuelve con un pitido corto.
3. Si tienes un monitor externo conectado, desconéctalo, reinicia el equipo y vuelve a conectarlo. Verifica que el monitor esté en la entrada correcta (HDMI, DisplayPort o USB-C).
4. Si la pantalla sigue negra pero se escucha el sistema, presiona Windows + P y elige "Solo pantalla de la PC" para forzar la salida del equipo.
5. Si el equipo queda negro en el logo de Windows, mantén presionado el botón de encendido 10 segundos y repite el encendido. Después de tres intentos fallidos, Windows abre el entorno de recuperación. Usa el paso 5 de la sección anterior.

## Mi PC va muy lenta, se congela o tarda en abrir las aplicaciones

Síntomas habituales: "el equipo está lentísimo", "se queda pegado", "tarda minutos en abrir Excel", "el ventilador suena fuerte y todo va lento".

1. Presiona Ctrl + Shift + Esc para abrir el Administrador de tareas. Haz clic en "Más detalles" si aparece la vista simple.
2. Revisa la pestaña Rendimiento. Si CPU, memoria o disco superan el 90 % de forma continua, identifica el proceso que consume más en la pestaña Procesos y ciérralo si no lo necesitas.
3. Ve a la pestaña Inicio. Deshabilita los programas con impacto "Alto" que no necesitas al encender el equipo.
4. Libera espacio en el disco: abre Configuración, Sistema, Almacenamiento, y elimina archivos temporales. Mantén al menos 15 % del disco libre.
5. Reinicia el equipo al final del día. Un equipo que no se reinicia durante semanas acumula procesos y actualizaciones pendientes.
6. Abre el Símbolo del sistema como administrador y ejecuta `sfc /scannow`. Luego ejecuta `DISM /Online /Cleanup-Image /RestoreHealth`. Cada comando puede tardar varios minutos. No cierres la ventana mientras corren.
7. Si el equipo sigue lento después de estos pasos, registra un ticket con la captura de la pestaña Rendimiento. Si el disco aparece al 100 % todo el tiempo, indícalo en el ticket.

## Pantalla azul (BSOD) con código de parada

Síntomas habituales: "me salió la pantalla azul", "dice que mi PC tuvo un problema y necesita reiniciarse", "salió un código en inglés con guiones bajos", "se reinicia sola y aparece una pantalla azul".

Windows muestra el nombre del error y un código hexadecimal, por ejemplo `0x000000EF`. Anota ambos antes de reiniciar. Si el equipo se reinicia solo, espera a que termine el inicio y revisa el mensaje en el visor de eventos o pide al colaborador que lo tome con su celular.

Tabla de códigos frecuentes y primera acción:

| Código y nombre | Causa habitual | Primera acción |
| --- | --- | --- |
| 0x0000007B INACCESSIBLE_BOOT_DEVICE | El disco o su controlador no responde al iniciar | Revisa cables o el modo del disco. Escala a INFRAESTRUCTURA. |
| 0x0000007A KERNEL_DATA_INPAGE_ERROR | Error de lectura del disco o del archivo de paginación | Ejecuta `chkdsk C: /f` y programa el chequeo al reiniciar. |
| 0x000000EF CRITICAL_PROCESS_DIED | Archivo de sistema dañado | Ejecuta `sfc /scannow` y luego DISM. |
| 0x0000003B SYSTEM_SERVICE_EXCEPTION | Controlador o actualización reciente | Desinstala el controlador o la actualización instalados el mismo día. |
| 0x000000D1 DRIVER_IRQL_NOT_LESS_OR_NOT_EQUAL | Controlador de red, audio o un periférico | Desactiva o actualiza el controlador en el Administrador de dispositivos. |
| 0x00000050 PAGE_FAULT_IN_NONPAGED_AREA | Memoria RAM o controlador defectuoso | Ejecuta el diagnóstico de memoria (mdsched.exe). |
| 0x0000001A MEMORY_MANAGEMENT | Error de memoria | Ejecuta el diagnóstico de memoria. Si repite, escala a INFRAESTRUCTURA. |
| 0x00000116 VIDEO_TDR_FAILURE | Controlador gráfico que dejó de responder | Reinstala o revierte el controlador de video. |
| 0x00000124 WHEA_UNCORRECTABLE_ERROR | Error de hardware (procesador, memoria o sobrecalentamiento) | No repitas el reinicio varias veces. Escala a INFRAESTRUCTURA con prioridad alta. |
| 0x00000133 DPC_WATCHDOG_VIOLATION | Disco de estado sólido o controlador de almacenamiento | Actualiza el controlador de almacenamiento y ejecuta `chkdsk`. |

Para el diagnóstico de memoria, guarda el trabajo, escribe "Diagnóstico de memoria de Windows" en el buscador y elige "Reiniciar ahora y buscar problemas". La prueba tarda unos minutos. No borres los archivos de la carpeta C:\Windows\Minidump, porque el equipo de soporte los necesita para analizar el error.

## Mi batería dura muy poco o no carga

Síntomas habituales: "la batería me dura una hora", "dice 20 % y se apaga", "no carga aunque esté enchufada", "el cargador calienta mucho".

1. Abre el Símbolo del sistema y ejecuta `powercfg /batteryreport`. El comando crea un archivo llamado battery-report.html en la carpeta desde la que lo ejecutaste.
2. Abre ese archivo en el navegador. Compara "Capacidad de carga completa" con "Capacidad de diseño". Si la capacidad actual es menor al 60 % de la de diseño, la batería está desgastada y debe reemplazarse. Registra un ticket para INFRAESTRUCTURA.
3. Para ganar autonomía mientras tanto, reduce el brillo, activa el modo de ahorro de energía desde el icono de batería y cierra programas que consumen mucho, como navegadores con muchas pestañas o videos en segundo plano.
4. Si la batería no carga, revisa que el cargador sea el original del equipo y que el cable no esté doblado en la punta. Revisa también si la luz del cargador se enciende. Si el cargador no enciende la luz, el cargador está dañado.
5. No intentes abrir la carcasa del equipo ni reemplazar la batería por tu cuenta. Esto anula la garantía y puede causar daños.

## Mi equipo se calienta, hace mucho ruido o se apaga de golpe

Síntomas habituales: "el ventilador suena como una aspiradora", "la base quema", "se apaga cuando trabajo con varias aplicaciones", "el equipo está muy caliente al tocarlo".

1. Trabaja con el equipo sobre una superficie plana y dura. Las cobijas, los cojines y las camas bloquean las rejillas de ventilación.
2. Revisa en el Administrador de tareas qué proceso consume CPU. Un proceso que llega al 100 % de forma constante genera calor. Ciérralo o reinícialo.
3. Revisa que el modo de energía no esté en "Máximo rendimiento" de forma permanente. Elige "Equilibrado" en Configuración, Sistema, Energía.
4. Apaga el equipo, desconecta el cargador y limpia las rejillas con un soplador de polvo en ráfagas cortas, sin introducir la boquilla dentro de la carcasa.
5. Si el equipo se apaga de golpe con el mensaje de temperatura, o si el problema continúa después de limpiarlo, registra un ticket para INFRAESTRUCTURA. Describe en qué programas trabajaba y si el equipo tiene más de tres años.

## Cuándo registrar el ticket

Registra el ticket si después de seguir este manual el equipo continúa igual, si aparece una pantalla azul que se repite, si el disco falla o si el equipo no enciende. Incluye el modelo, el número de serie, el código de error o la captura de pantalla y los pasos que ya hiciste. No envíes contraseñas en el ticket.
