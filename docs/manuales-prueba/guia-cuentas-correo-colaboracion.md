# Guía de cuentas, correo y colaboración

Empresa Demo S.A.C. — Mesa de Ayuda de TI. Versión 2.3, octubre de 2026.

Esta guía resuelve los incidentes más frecuentes con la cuenta corporativa, la verificación en dos pasos, Outlook, Microsoft Teams y OneDrive. Si después de seguir los pasos el problema continúa, registra un ticket en TraceHelp y adjunta una captura del mensaje de error.

## Restablecer la contraseña

La contraseña de la cuenta corporativa vence cada 90 días. Desde 10 días antes, Windows muestra el aviso "Tu contraseña expirará pronto". Cámbiala antes de que venza para no perder el acceso al correo y a la VPN.

Para cambiarla estando en la oficina o conectado a la VPN, presiona Ctrl + Alt + Supr y elige "Cambiar una contraseña". Para restablecerla si la olvidaste, entra al portal de autoservicio https://passwordreset.microsoftonline.com, escribe tu correo corporativo y valida tu identidad con el código que llega a tu celular registrado.

La nueva contraseña debe tener al menos 12 caracteres, con mayúsculas, minúsculas y números, y no puede repetir ninguna de las últimas 5 contraseñas. No uses tu nombre, tu DNI ni el nombre de la empresa.

Después de cambiarla, cierra sesión en todos tus equipos. En el celular, Outlook y Teams pedirán la nueva contraseña; si no la piden en 10 minutos, quita la cuenta de la aplicación y vuelve a agregarla.

## Cuenta bloqueada

La cuenta se bloquea durante 15 minutos después de 5 intentos fallidos de inicio de sesión. El mensaje en Windows es "La cuenta a la que se hace referencia está bloqueada y no se puede iniciar sesión en ella". En el correo web aparece "Tu cuenta se bloqueó temporalmente para evitar un uso no autorizado".

Espera 15 minutos y vuelve a intentarlo con cuidado: revisa que Bloq Mayús esté desactivado y que el teclado esté en español. Si no recuerdas la contraseña, restablécela desde el portal de autoservicio en lugar de seguir intentando, porque cada intento fallido reinicia el contador.

Si la cuenta se bloquea sola varias veces al día, casi siempre es un dispositivo con la contraseña antigua guardada que sigue intentando conectarse: un celular con el correo configurado, una sesión abierta en otra laptop o una unidad de red mapeada con credenciales guardadas. Revisa el celular primero. En Windows, abre "Administrador de credenciales", elimina las credenciales de Windows que mencionen el dominio DEMO y vuelve a iniciar sesión.

## Verificación en dos pasos (MFA)

Todas las cuentas usan verificación en dos pasos con la aplicación Microsoft Authenticator. Al iniciar sesión desde un equipo nuevo o fuera de la oficina, aparece el mensaje "Aprobar solicitud de inicio de sesión" y un número de dos dígitos que debes escribir en el celular.

Si no te llega la notificación, abre Microsoft Authenticator y desliza hacia abajo para actualizar. Revisa que el celular tenga la hora automática activada: si la hora del celular está adelantada o atrasada, los códigos de seis dígitos no funcionan y aparece el error "El código de verificación no es válido".

Si cambiaste de celular, perdiste el equipo o desinstalaste la aplicación, no podrás aprobar el inicio de sesión. Registra un ticket desde otra persona del área o llama al anexo 4000; un analista validará tu identidad y restablecerá los métodos de verificación. Por seguridad, este restablecimiento nunca se hace por correo.

## Outlook no se conecta

Si Outlook muestra "Desconectado" o "Intentando conectar" en la barra inferior, revisa primero que tengas internet abriendo cualquier página web. Si el internet funciona, haz clic en Archivo, luego en Configuración de la cuenta, y verifica que el estado de la cuenta no diga "Se requiere contraseña".

Si Outlook pide la contraseña una y otra vez, aunque la escribas bien, cierra Outlook, abre "Administrador de credenciales" de Windows, elimina las credenciales que empiecen con "MicrosoftOffice16_Data" y vuelve a abrir Outlook. Esto ocurre con frecuencia después de cambiar la contraseña.

Cuando Outlook se abre pero no muestra correos nuevos o muestra carpetas vacías, el archivo de datos local (.ost) puede estar dañado. Cierra Outlook, entra a Panel de control, Correo, Archivos de datos, abre la ubicación del archivo y cambia el nombre del archivo .ost agregando ".old" al final. Al abrir Outlook se descargará el buzón de nuevo; con un buzón grande puede tardar hasta una hora.

## Buzón lleno

Cada buzón tiene 50 GB. Al llegar al 90 % aparece el aviso "Tu buzón está casi lleno" y al llegar al 100 % ya no puedes enviar correos; el mensaje de error es "No se puede enviar este mensaje porque el buzón está lleno".

Para liberar espacio, vacía la carpeta Elementos eliminados y la carpeta Correo no deseado, y busca los correos con adjuntos grandes escribiendo "tamaño:enorme" en la barra de búsqueda de Outlook. Guarda los adjuntos importantes en OneDrive antes de borrar los correos. Si necesitas conservar todo el historial, solicita la activación del archivo en línea mediante un ticket.

## Microsoft Teams: audio y cámara

Si en una reunión de Teams no te escuchan o no escuchas a los demás, haz clic en "Más", luego en "Configuración del dispositivo", y elige el micrófono y los altavoces correctos. Los auriculares USB a veces aparecen con otro nombre, por ejemplo "Headset" o el nombre del fabricante.

Si la cámara aparece en negro, revisa que la tapa física de la cámara esté abierta y que ninguna otra aplicación la esté usando. En Windows, abre Configuración, Privacidad y seguridad, Cámara, y confirma que el acceso de las aplicaciones esté activado.

Cuando Teams se queda cargando o muestra "Ocurrió un problema", ciérralo desde el ícono de la barra de tareas con "Salir", borra la caché eliminando el contenido de la carpeta %appdata%\Microsoft\Teams y vuelve a abrirlo. No se pierden chats ni archivos, porque están en la nube.

## OneDrive no sincroniza

El ícono de nube de OneDrive en la barra de tareas indica el estado: una cruz roja significa error de sincronización y dos flechas significan que está sincronizando. Haz clic en el ícono para ver qué archivo tiene el problema.

Los errores más comunes son los nombres de archivo con caracteres no permitidos (por ejemplo " * : < > ? / \ |), las rutas de más de 400 caracteres y los archivos abiertos en otra aplicación. Cambia el nombre del archivo, acorta la ruta moviendo la carpeta a un nivel superior o cierra el archivo, y la sincronización se reanuda sola.

Si aparece "No hay espacio suficiente en OneDrive", cada usuario tiene 1 TB; revisa la papelera de reciclaje de OneDrive en la web, porque los archivos borrados siguen ocupando espacio durante 93 días.

## Cuándo registrar un ticket

Registra un ticket en TraceHelp si después de seguir esta guía el problema continúa, si el mensaje de error no aparece aquí o si el problema afecta a varias personas de tu área al mismo tiempo. Indica a quién afecta el problema, adjunta una captura del error y describe qué pasos ya intentaste. Nunca escribas tu contraseña en el ticket ni la envíes por correo o chat: el equipo de TI jamás te la pedirá.
