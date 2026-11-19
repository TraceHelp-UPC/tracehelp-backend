# Respaldo y recuperación: OneDrive no sincroniza, error 0x8004de40, archivos borrados, papelera, permisos de SharePoint y cuotas

Empresa Demo S.A.C. — Mesa de Ayuda de TI. Versión 1.0, noviembre de 2026.

Este manual explica cómo proteger y recuperar los archivos de trabajo. Cubre la sincronización de OneDrive, el error 0x8004de40 al iniciar sesión, la recuperación de archivos borrados desde la papelera o con historial de versiones, los permisos de los sitios de SharePoint y el espacio disponible en cada cuenta. Los archivos de trabajo deben guardarse en OneDrive o en SharePoint, no solo en el escritorio del equipo, porque así tienen copia y pueden recuperarse.

## OneDrive no sincroniza mis archivos

Síntomas habituales: "mis archivos no se actualizan en la nube", "OneDrive dice que hay un problema de sincronización", "el ícono de OneDrive tiene una cruz roja", "los cambios de mi equipo no aparecen en la otra laptop".

El ícono de nube de OneDrive, en la barra de tareas, muestra el estado. Una cruz roja significa error de sincronización. Dos flechas significan que está sincronizando. Un check verde significa que todo está al día.

1. Haz clic en el ícono de OneDrive y revisa el mensaje. El sistema indica el archivo que tiene el problema.
2. Revisa el nombre del archivo. OneDrive no acepta los caracteres " * : < > ? / \ |. Cambia el nombre quitando esos caracteres.
3. Revisa la longitud de la ruta. Las rutas de más de 400 caracteres no se sincronizan. Acorta la ruta moviendo la carpeta a un nivel superior.
4. Cierra el archivo si está abierto en otra aplicación. Un archivo abierto puede bloquear la sincronización hasta que se cierre.
5. Espera unos minutos. La sincronización se reanuda sola cuando el problema se corrige.
6. Si el ícono sigue en error, abre el menú de OneDrive, elige Configuración, y pausa y reanuda la sincronización.
7. Si sigue igual, reinicia el equipo. Si el problema continúa, registra un ticket para APLICACIONES con el nombre del archivo afectado (sin datos confidenciales) y la captura del mensaje.

## OneDrive muestra el error 0x8004de40 al iniciar sesión

Síntomas habituales: "OneDrive no me deja iniciar sesión", "aparece el código 0x8004de40", "dice que no se puede conectar con OneDrive", "la configuración de OneDrive se queda en blanco".

El código 0x8004de40 aparece cuando el cliente de OneDrive no puede comunicarse con el servicio para iniciar sesión. Las causas más comunes son una conexión de red interrumpida, una fecha u hora del equipo incorrecta, un proxy mal configurado o un cliente de OneDrive desactualizado.

1. Revisa que el equipo tenga internet. Abre una página web conocida de la empresa. Si no abre, sigue el manual de red.
2. Revisa la fecha y la hora. Abre Configuración, Hora e idioma, y activa "Establecer la hora automáticamente" y "Establecer la zona horaria automáticamente". Una hora incorrecta impide iniciar sesión.
3. Revisa el proxy en Configuración, Red e Internet, Proxy. No cambies la configuración si el equipo la tiene por política; registra un ticket para REDES en ese caso.
4. Cierra OneDrive desde el ícono de la barra de tareas con "Salir de OneDrive". Abre el cuadro Ejecutar con Windows + R y escribe `%localappdata%\Microsoft\OneDrive\onedrive.exe /reset`. Espera un minuto.
5. Vuelve a abrir OneDrive desde el menú Inicio. Inicia sesión con tu cuenta corporativa completa.
6. El comando de restablecimiento no borra tus archivos. Solo reinicia el cliente de sincronización.
7. Si el error continúa, registra un ticket para APLICACIONES con el código 0x8004de40, la hora del intento y el modelo del equipo.

## Quiero recuperar un archivo que borré

Síntomas habituales: "borré sin querer un archivo de la carpeta compartida", "no encuentro mi Excel, lo eliminé", "se borró la carpeta de Documentos", "necesito la versión de ayer del archivo".

Hay tres lugares donde un archivo borrado puede estar, y conviene revisarlos en este orden:

1. La papelera de reciclaje del equipo. Abre la papelera desde el escritorio, busca el archivo, haz clic derecho y elige "Restaurar". Los archivos borrados de OneDrive desde el equipo también pasan por aquí durante un tiempo.
2. La papelera de OneDrive o de SharePoint en la web. Entra a tu OneDrive desde el navegador con tu cuenta corporativa, abre el menú de la izquierda y elige "Papelera de reciclaje". Selecciona el archivo y elige "Restaurar". Los archivos permanecen en la papelera 93 días.
3. El historial de versiones. Si el archivo sigue en la carpeta pero con un contenido equivocado o dañado, haz clic derecho sobre el archivo en OneDrive o SharePoint, elige "Versiones" o "Historial de versiones" y restaura la versión que necesitas.

Si el archivo no aparece en ninguno de los tres lugares después de 93 días, o si borraste una carpeta completa con muchos archivos, registra un ticket para INFRAESTRUCTURA. La restauración desde respaldos del servidor requiere aprobación y puede tardar varios días. Indica el nombre de la carpeta, la ruta aproximada y la fecha en que el archivo estaba en buen estado.

No intentes recuperar archivos con programas de recuperación que encuentres en internet. Pueden dañar el disco y perder la información.

## Archivos de mi equipo que no están en la nube

Síntomas habituales: "guardé en el escritorio y no sale en OneDrive", "mis fotos o documentos no están respaldados", "cambié de equipo y no encuentro mis archivos".

Los archivos del escritorio, de Documentos y de Imágenes pueden protegerse con la copia de seguridad de carpetas de OneDrive.

1. Haz clic en el ícono de OneDrive y elige Configuración, luego Copia de seguridad, y "Administrar copia de seguridad".
2. Activa las carpetas Escritorio, Documentos e Imágenes que quieras proteger.
3. Revisa que el ícono de OneDrive muestre el check verde para esas carpetas.

Si el equipo tiene activado el historial de archivos de Windows, puedes recuperar versiones anteriores escribiendo "Historial de archivos" en el buscador de Windows y eligiendo "Restaurar archivos personales". Si no está activado, registra un ticket para que el analista lo configure.

## Permisos de SharePoint: no puedo abrir el sitio o el archivo

Síntomas habituales: "me dice que no tengo acceso al sitio", "no puedo abrir la carpeta de un proyecto", "solo puedo ver el archivo, no editarlo", "el enlace dice que solicite acceso".

Los sitios de SharePoint tienen dueños que aprueban los accesos. El permiso se asigna al grupo o a la persona, no a un equipo.

1. Abre el enlace del sitio o del archivo desde el navegador con tu cuenta corporativa. Si aparece "Solicitar acceso", haz clic y escribe el motivo.
2. Si necesitas editar y solo puedes ver, pide el permiso de edición al dueño del sitio o del archivo. El dueño puede verlo en "Administrar acceso".
3. Si el sitio pertenece a otra área y no sabes quién es el dueño, registra un ticket para APLICACIONES indicando el nombre del sitio y la razón del acceso.
4. No compartas tu contraseña para que otra persona abra el archivo. Usa el enlace compartido por el dueño.
5. Si un archivo se comparte con personas de fuera de la empresa y no deberían tenerlo, registra un incidente para SEGURIDAD.

## Mi cuenta de OneDrive o SharePoint no tiene espacio

Síntomas habituales: "OneDrive dice que no hay espacio suficiente", "no puedo subir más archivos", "el sitio de SharePoint no acepta cargar archivos", "la sincronización se detuvo por cuota".

1. Cada usuario tiene 1 TB de espacio en OneDrive. Revisa cuánto ocupa en la web, en Configuración, Almacenamiento.
2. Vacía la papelera de reciclaje de OneDrive solo si ya no necesitas esos archivos. Los archivos borrados siguen ocupando espacio durante 93 días.
3. Revisa carpetas con videos o respaldos grandes que puedan moverse a otro lugar aprobado por tu jefe.
4. Los sitios de SharePoint tienen cuota asignada por el administrador del sitio. Si el sitio llega al límite, registra un ticket para APLICACIONES con el nombre del sitio y el tamaño actual. No cambies la cuota por tu cuenta.
5. No guardes copias de respaldo personales de la empresa en discos externos sin autorización.

## Respaldos de servidor y restauración de grandes volúmenes

Los respaldos de los servidores de archivos de la empresa se realizan de forma automática. La restauración de un volumen completo, de una carpeta compartida de la red o de un servidor requiere un ticket de INFRAESTRUCTURA y la aprobación del jefe del área afectada. Indica el nombre de la carpeta de red, la fecha a la que se quiere volver y el motivo de la restauración.

## Cuándo registrar el ticket

Registra el ticket si OneDrive sigue en error después de seguir este manual, si aparece el código 0x8004de40 después del restablecimiento, si el archivo no está en la papelera ni en el historial de versiones, si no tienes permisos para un sitio de SharePoint o si el espacio de tu cuenta se agotó. Indica el nombre del archivo o del sitio (sin contraseñas ni datos confidenciales), la ruta aproximada, el código de error y la hora del último cambio que recuerdas.
