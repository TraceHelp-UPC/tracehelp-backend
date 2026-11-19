# Software: instalar, desinstalar, licencias de Office, actualizaciones y permisos de administrador

Empresa Demo S.A.C. — Mesa de Ayuda de TI. Versión 1.0, noviembre de 2026.

Este manual resuelve las consultas de software de los colaboradores: cómo instalar o quitar un programa, qué hacer con los errores de instalación como 0x80070643, por qué Windows Update no descarga actualizaciones (0x80240034), cómo revisar la licencia de Office y cuándo se necesitan permisos de administrador. Los pasos se pueden seguir sin privilegios de administrador, salvo que se indique lo contrario.

## Quiero instalar un programa

Síntomas habituales: "necesito instalar un programa para mi trabajo", "dónde descargo el programa", "me pide permisos para instalar".

1. Revisa primero el Portal de aplicaciones de la empresa. Los programas aprobados aparecen ahí y se instalan sin pedir permisos de administrador.
2. Si el programa no aparece en el catálogo, registra un ticket de tipo "Solicitud de software" con el nombre exacto del programa, la versión, la justificación de negocio y el nombre de tu jefe directo que la aprueba.
3. No descargues instaladores de sitios que no conozcas. Los instaladores gratuitos de fuentes no oficiales son una de las causas más comunes de malware en los equipos.
4. Después de la aprobación, el analista instala el programa o te da permiso para instalarlo desde el portal. No compartas tu cuenta para que otra persona lo instale.

## Quiero desinstalar un programa

Síntomas habituales: "quiero quitar un programa que ya no uso", "el programa se cierra y no puedo borrarlo", "aparece un botón gris al desinstalar".

1. Abre Configuración, luego Aplicaciones, y elige Aplicaciones instaladas.
2. Busca el programa, haz clic en los tres puntos y elige Desinstalar. Sigue las instrucciones de la ventana.
3. Si el botón Desinstalar aparece en gris, el programa requiere permisos de administrador. Registra un ticket indicando el nombre del programa.
4. Si el programa no se desinstala y muestra un error, reinicia el equipo, cierra todas las aplicaciones y vuelve a intentarlo. Si sigue igual, registra un ticket para APLICACIONES.

## Error 0x80070643 al instalar o actualizar un programa

Síntomas habituales: "la instalación se detuvo con el código 0x80070643", "Error de instalación con código 0x80070643", "la actualización de Office no termina", "el instalador de .NET falla".

El código 0x80070643 significa que la instalación de un paquete falló. Suele ocurrir cuando una instalación anterior quedó a medias, cuando un componente como .NET Framework está dañado o cuando el equipo no tiene espacio suficiente en el disco.

1. Reinicia el equipo y vuelve a intentar la instalación. Muchas instalaciones fallidas se resuelven con este paso.
2. Revisa que haya al menos 10 GB libres en el disco C. Si no los hay, libera espacio desde Configuración, Sistema, Almacenamiento.
3. Ejecuta el instalador haciendo clic derecho y eligiendo "Ejecutar como administrador". Si aparece la ventana de control de cuentas de usuario, acepta solo si el programa es el que estás instalando y pediste la instalación.
4. Si el programa ya estaba instalado, repáralo: abre Configuración, Aplicaciones, Aplicaciones instaladas, elige el programa, haz clic en los tres puntos y selecciona Modificar. En Microsoft Office elige "Reparación rápida". Si la reparación rápida no alcanza, elige "Reparación en línea".
5. Abre el Símbolo del sistema como administrador y ejecuta `sfc /scannow`. Si el comando indica que encontró archivos dañados que no pudo reparar, ejecuta `DISM /Online /Cleanup-Image /RestoreHealth` y repite `sfc /scannow`.
6. Si el error continúa, anota el código completo y registra un ticket para APLICACIONES. Adjunta el nombre del programa, la versión y una captura del mensaje.

## Windows Update no descarga actualizaciones: error 0x80240034

Síntomas habituales: "Windows Update dice que no se pudieron instalar las actualizaciones", "aparece el código 0x80240034", "la descarga se queda en cero", "la actualización de Windows lleva días pendiente".

El código 0x80240034 indica que la descarga de la actualización falló. Casi siempre se debe a una conexión interrumpida, a poco espacio en disco, a un proxy que bloquea la descarga o a una carpeta de actualizaciones dañada.

1. Revisa que el equipo tenga internet y que no esté conectado a una red de visitantes que pida inicio de sesión. Si el problema es la red, sigue el manual de red.
2. Revisa que haya al menos 10 GB libres en el disco C.
3. Abre Configuración, Sistema, Solucionar problemas, Otros solucionadores de problemas, y ejecuta el solucionador de Windows Update.
4. Reinicia el equipo y vuelve a buscar actualizaciones desde Configuración, Windows Update, "Buscar actualizaciones".
5. Si el error continúa, restablece la carpeta de descargas. Abre el Símbolo del sistema como administrador y ejecuta, en este orden: `net stop wuauserv`, `net stop bits`, `ren C:\Windows\SoftwareDistribution SoftwareDistribution.old`, `net start bits` y `net start wuauserv`. Luego reinicia el equipo.
6. No borres la carpeta SoftwareDistribution.old hasta que las actualizaciones se instalen sin errores durante una semana.
7. Si después de estos pasos el error se repite, registra un ticket para INFRAESTRUCTURA indicando la hora del último intento y el código completo.

No pauses las actualizaciones por tu cuenta durante más de siete días. Las actualizaciones de seguridad corrigen vulnerabilidades que se usan en ataques reales.

## Licencia de Office no válida o producto sin activar

Síntomas habituales: "Office dice que este producto no tiene licencia", "Word muestra el mensaje Modo de funcionalidad reducida", "me pide una clave de producto", "aparece el código 0xC004F074".

Office de la empresa se activa con la cuenta corporativa. No necesitas una clave de producto ni debes buscar claves en internet.

1. Abre Word, Excel u Outlook, y ve a Archivo, luego Cuenta.
2. Revisa el estado de la licencia. Si dice "Producto sin licencia" o pide iniciar sesión, haz clic en "Iniciar sesión" y usa tu cuenta corporativa completa. No uses cuentas personales.
3. Cierra todas las aplicaciones de Office y vuelve a abrirlas. La licencia se valida al iniciar.
4. Si aparece el código 0xC004F074, el equipo no pudo contactar al servicio de activación de la empresa. Conéctate a la red corporativa o a la VPN y repite el paso 2. Si sigue igual, registra un ticket para APLICACIONES.
5. Para revisar la activación de Windows, abre el Símbolo del sistema y ejecuta `slmgr /xpr`. El comando muestra si Windows está activado de forma permanente. Si no lo está, registra un ticket. No ejecutes comandos de activación que encuentres en internet.
6. No compartas la cuenta corporativa ni pegues claves de producto en correos o chats. Eso es una brecha de seguridad y se reporta como incidente.

## Necesito permisos de administrador para instalar o cambiar algo

Síntomas habituales: "me pide una contraseña de administrador", "el sistema dice que necesitas permisos del administrador", "no me deja cambiar la configuración de red", "la ventana de control de cuentas de usuario aparece cada vez".

Los colaboradores trabajan con una cuenta estándar. Esto protege el equipo de cambios no autorizados. Cuando una tarea necesita permisos elevados, el proceso correcto es el siguiente:

1. Registra un ticket de tipo "Solicitud de privilegios elevados". Indica la tarea que necesitas realizar, el programa o la configuración, el tiempo que necesitas los permisos y la aprobación de tu jefe directo.
2. El analista evaluará la solicitud. Si se aprueba, se hará la instalación o se asignará un permiso temporal con fecha de fin.
3. No escribas la contraseña de un administrador en la ventana de control de cuentas de usuario sin autorización. Si la piden y no fuiste tú quien inició la acción, cancela y registra un incidente para SEGURIDAD.
4. Nunca uses la cuenta de otro colaborador ni compartas tu contraseña para instalar programas.

## Mi programa de Office no abre o se cierra al iniciar

Síntomas habituales: "Excel se cierra sola", "después de la última actualización Word no funciona".

1. Cierra el programa desde el Administrador de tareas (Ctrl + Shift + Esc) y vuelve a abrirlo.
2. Reinicia el equipo para completar cualquier actualización pendiente.
3. En Office, revisa Archivo, Cuenta, Opciones de actualización, y elige "Actualizar ahora".
4. Si el programa sigue sin abrir, registra un ticket para APLICACIONES con el nombre y la versión del programa y el texto del error.

## Cuándo registrar el ticket

Registra el ticket si el programa no se instala después de seguir este manual, si necesitas permisos de administrador, si Office sigue sin licencia o si Windows Update falla dos veces seguidas. Indica el nombre del programa, la versión, el código de error completo y los pasos que ya intentaste. Nunca escribas tu contraseña ni la de otro colaborador en el ticket.
