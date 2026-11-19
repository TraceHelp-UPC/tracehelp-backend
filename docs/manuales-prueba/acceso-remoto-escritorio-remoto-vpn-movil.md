# Acceso remoto: escritorio remoto (RDP), VPN desde el celular, verificación MFA y trabajo desde casa

Empresa Demo S.A.C. — Mesa de Ayuda de TI. Versión 1.0, noviembre de 2026.

Este manual explica cómo conectarse a tu equipo de trabajo desde otro lugar. Cubre el escritorio remoto (RDP) con los códigos de error 0x904 y 0x708, la VPN en el celular, la aprobación de MFA cuando estás fuera de la oficina y las reglas para trabajar desde casa. Para los errores de la VPN de computadora (809, 691, 789 y 868), consulta el manual de soporte técnico en PDF. Antes de empezar, verifica que tu cuenta corporativa funcione y que tu celular tenga Microsoft Authenticator instalado.

## Escritorio remoto: no me conecta a mi equipo de la oficina

Síntomas habituales: "me sale un error al conectarme al escritorio remoto", "dice error 0x904", "aparece el código 0x708 y no entra", "la conexión de escritorio remoto no se establece", "me pide la contraseña y no la acepta".

El escritorio remoto solo funciona si el equipo de la oficina está encendido, si tu equipo tiene conexión a la red y si tu usuario tiene permiso para entrar. Cuando la conexión falla, la ventana muestra un código hexadecimal. Los códigos 0x904 y 0x708 se atienden con los mismos pasos de verificación, que cubren las causas más comunes: red, credenciales y permisos.

1. Confirma que estás conectado a la VPN corporativa o, si estás en la oficina, a la red de la empresa. Sin VPN, el equipo de la oficina no responde desde fuera.
2. Revisa que el nombre del equipo de destino esté bien escrito. Pide el nombre exacto al analista o revisa la etiqueta del equipo. No uses la dirección IP si la mesa te indicó el nombre.
3. Abre la aplicación Conexión a Escritorio remoto (escribe "mstsc" en el buscador de Windows), escribe el nombre del equipo y haz clic en Conectar.
4. Cuando pida credenciales, escribe tu usuario corporativo completo y tu contraseña actual. Si cambiaste la contraseña hace poco, usa la nueva y revisa que Bloq Mayús esté desactivado.
5. Si la ventana dice que el equipo no está disponible, comprueba que el equipo de la oficina esté encendido. Pide a un colaborador de la oficina que lo revise. Nunca apagues el equipo de la oficina de forma remota.
6. Si aparecen las credenciales guardadas de una conexión anterior y ya no funcionan, abre Administrador de credenciales de Windows, busca las credenciales que mencionen el nombre del equipo de la oficina y elimínalas. Vuelve a conectarte.
7. Si el mensaje indica que otro usuario tiene una sesión abierta en el equipo, avisa a la persona que está en la oficina antes de cerrar su sesión. Si no hay nadie, registra un ticket para el analista.
8. Si el error continúa después de seguir estos pasos, registra un ticket para REDES si el problema es la conexión, o para APLICACIONES si el problema es el escritorio remoto. Indica el código exacto, la hora y el nombre del equipo de destino (no la contraseña).

## Mi usuario no tiene permiso para el escritorio remoto

Síntomas habituales: "me dice que no tengo permiso para conectarme de forma remota", "la conexión se cierra apenas pongo la contraseña", "antes me conectaba y ahora no".

Los permisos de escritorio remoto se asignan por solicitud. No se activan por tu cuenta.

1. Registra un ticket de tipo "Solicitud de acceso remoto". Indica el equipo de destino, el motivo y la aprobación de tu jefe directo.
2. El analista revisa la solicitud. Si se aprueba, tu usuario se agrega al grupo de acceso remoto del equipo.
3. Después de que te agreguen al grupo, cierra sesión en tu equipo y vuelve a iniciar sesión antes de conectarte.

## VPN en el celular: quiero entrar a los sistemas desde el teléfono

Síntomas habituales: "necesito la VPN en el celular", "no encuentro la VPN en el teléfono", "el celular dice que la conexión falló", "la VPN del celular se desconecta sola".

La VPN del celular usa el cliente corporativo aprobado. Solo instala la aplicación desde la tienda oficial de tu teléfono y desde el enlace que te indique la mesa de ayuda.

En Android:

1. Instala el cliente VPN corporativo desde Google Play. Si no aparece, pide la instalación por ticket.
2. Abre la aplicación, escribe el servidor que te indique la mesa de ayuda y elige "Conectar".
3. Inicia sesión con tu cuenta corporativa completa. Aprueba la solicitud en Microsoft Authenticator cuando aparezca.
4. Revisa que el ícono de llave o VPN aparezca en la barra superior del teléfono. Eso confirma la conexión.

En iPhone:

1. Instala el cliente VPN corporativo desde la App Store.
2. Abre la aplicación, agrega el perfil que te indique la mesa de ayuda y acepta la instalación del perfil en Ajustes.
3. Inicia sesión con tu cuenta corporativa y aprueba el MFA.

Si la VPN del celular se desconecta cada pocos minutos, revisa que la opción de ahorro de batería no esté restringiendo la aplicación. En Android, desactiva la optimización de batería para la app VPN. En iPhone, revisa que la opción de datos en segundo plano esté activada para la app.

Si el celular dice que la conexión falló, revisa tus datos móviles o tu conexión Wi-Fi. Si la conexión funciona para otras aplicaciones y la VPN no conecta, registra un ticket para REDES con el modelo del celular y la versión de la aplicación.

## Verificación en dos pasos (MFA): no me llega la aprobación fuera de la oficina

Síntomas habituales: "no me llega la notificación de Authenticator", "cambié de celular y no puedo aprobar el inicio de sesión", "aprobé pero no entra", "me pide un código de seis dígitos y no funciona".

La verificación en dos pasos es obligatoria para acceder desde fuera de la oficina. Usa Microsoft Authenticator en tu celular.

1. Abre Microsoft Authenticator y desliza hacia abajo para actualizar la lista de solicitudes.
2. Revisa que el celular tenga la fecha y la hora automáticas activadas. Un celular con hora incorrecta genera códigos de seis dígitos que no funcionan.
3. Revisa que tengas conexión de datos o Wi-Fi. Las notificaciones llegan solo si el celular está conectado.
4. Si la aplicación pidió el número de dos dígitos, escríbelo en la pantalla del equipo que estás usando. No apruebes solicitudes que no hiciste.
5. Si cambiaste de celular, perdiste el teléfono o desinstalaste Authenticator, no podrás aprobar el inicio de sesión. Registra un ticket desde otra persona de tu área o llama al anexo 4000. Un analista validará tu identidad y restablecerá tus métodos de verificación. Este restablecimiento nunca se hace por correo.
6. Si recibes solicitudes de aprobación que no reconoces, recházalas y registra un incidente para SEGURIDAD. Es posible que alguien tenga tu contraseña.

Para más detalles de MFA y bloqueos, consulta la guía de cuentas, correo y colaboración.

## Trabajo desde casa: qué debo tener y cómo conectarme

Síntomas habituales: "quiero trabajar desde casa", "mi laptop personal no se conecta a los sistemas", "necesito saber qué se requiere para teletrabajar", "la conexión en casa es lenta".

Para trabajar desde casa necesitas:

- Un equipo corporativo con el antivirus activado y las actualizaciones al día. Los equipos personales no se usan para acceder a los sistemas de la empresa.
- Conexión a internet estable. Si la conexión se corta con frecuencia, prueba el cable de red del router o registra un ticket para REDES.
- Cliente VPN corporativo instalado y verificación en dos pasos configurada.
- Cuenta corporativa completa, sin compartirla con otras personas del hogar.

Reglas de seguridad:

1. Conéctate siempre a la VPN antes de abrir los sistemas de la empresa o el escritorio remoto.
2. No uses redes Wi-Fi públicas sin VPN. Si necesitas trabajar fuera de casa, usa los datos del celular como punto de acceso con VPN activa.
3. Bloquea la pantalla con Windows + L cuando te alejes del equipo, aunque estés en casa.
4. No guardes documentos de la empresa en carpetas personales ni en memorias USB sin cifrar.
5. Si tu conexión en casa es lenta, cierra las descargas y el streaming mientras trabajas, o usa el cable de red del router.
6. Si necesitas una impresora o un periférico de la oficina desde casa, registra un ticket. No compartas la impresora de la oficina con la red de tu casa por cuenta propia.

## Cuándo registrar el ticket

Registra el ticket si el escritorio remoto o la VPN no conectan después de seguir este manual, si no te llega la aprobación de MFA, si cambiaste de celular o si necesitas un permiso de acceso remoto. Indica el código de error completo, el tipo de conexión (escritorio remoto, VPN de computadora o VPN de celular), el modelo del celular o del equipo y la hora del intento. Nunca envíes contraseñas ni códigos de verificación en el ticket.
