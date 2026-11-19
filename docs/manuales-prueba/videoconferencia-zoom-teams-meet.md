# Videoconferencia: cámara, micrófono, pantalla compartida, inicio de sesión y error caa70004 en Teams

Empresa Demo S.A.C. — Mesa de Ayuda de TI. Versión 1.0, noviembre de 2026.

Este manual resuelve los incidentes de las reuniones virtuales: la cámara no funciona o sale negra, el micrófono no se escucha, no puedes compartir pantalla, no puedes iniciar sesión en la aplicación de reuniones, la calidad del audio es mala o Microsoft Teams muestra el error caa70004. La empresa usa Microsoft Teams como herramienta principal. Zoom y Google Meet se usan solo con reuniones de clientes o proveedores que los solicitan. Los pasos sirven para las tres aplicaciones salvo que se indique lo contrario.

## No me escuchan en la reunión o no escucho a los demás

Síntomas habituales: "en la reunión no me escuchan", "no oigo a nadie", "mi voz se corta", "dicen que hay eco", "me escuchan con retraso".

1. Revisa que el micrófono no esté silenciado. En Teams, el ícono del micrófono debe estar sin línea roja. En Zoom y Meet, revisa el mismo ícono en la barra inferior.
2. Dentro de la reunión, abre el menú de configuración de dispositivos (en Teams, los tres puntos y Configuración del dispositivo) y elige el micrófono y el altavoz correctos. Los auriculares USB o Bluetooth suelen aparecer con otro nombre, por ejemplo "Headset" o el nombre del fabricante.
3. Usa el botón de prueba del altavoz y del micrófono. Di algunas frases y revisa que la barra de volumen se mueva.
4. Si hay eco, usa auriculares en lugar de los altavoces de la laptop. Si hay varias personas en el mismo espacio con altavoces encendidos, pide que silencien sus micrófonos cuando no hablan.
5. Si el audio se corta, cierra las descargas o los videos que estén usando la red al mismo tiempo, y acerca el equipo al router o conéctate por cable.
6. Si después de cambiar el dispositivo sigue sin escucharse, cierra la reunión, reinicia la aplicación y vuelve a entrar. Si persiste, registra un ticket para APLICACIONES.

## La cámara aparece en negro o no aparece

Síntomas habituales: "la cámara sale negra", "no me ven en la reunión", "la cámara dice que está en uso", "no aparece ninguna cámara", "en Teams aparece el mensaje caa70004".

1. Revisa que la tapa física de la cámara esté abierta o que el interruptor de privacidad esté activado, si el equipo lo tiene.
2. Cierra todas las aplicaciones que puedan estar usando la cámara: otra reunión, un programa de grabación o la aplicación de fotos.
3. En Windows, abre Configuración, Privacidad y seguridad, Cámara, y confirma que el acceso a la cámara esté activado. Revisa también que Teams o la aplicación que usas tenga permiso.
4. Dentro de la reunión, elige la cámara correcta en la configuración de dispositivos.
5. Cierra por completo la aplicación desde el ícono de la barra de tareas, no solo la ventana, y vuelve a abrirla.
6. Si la cámara sigue en negro, reinicia el equipo. Si aparece en el Administrador de dispositivos con un signo de advertencia, consulta el manual de periféricos.

## Error caa70004 en Microsoft Teams

Síntomas habituales: "Teams muestra el código caa70004", "dice que no puede acceder a la cámara", "al unirme a la reunión sale un error de cámara", "Teams no encuentra la cámara aunque está conectada".

El código caa70004 indica que Teams no pudo usar la cámara. Casi siempre la cámara está ocupada por otra aplicación, o el sistema no le dio permiso a Teams.

1. Cierra la reunión y verifica que no tengas abierta otra aplicación de video. Revisa también otras pestañas del navegador que puedan usar la cámara, como una reunión de Meet o de Zoom.
2. Abre Configuración, Privacidad y seguridad, Cámara, y confirma que el acceso a la cámara para las aplicaciones de escritorio esté activado.
3. Cierra Teams desde el ícono de la barra de tareas con "Salir". Espera diez segundos y vuelve a abrirlo.
4. Si el error persiste, borra la caché de Teams. Cierra Teams por completo, abre el cuadro de ejecución con Windows + R, escribe `%appdata%\Microsoft\Teams` y elimina el contenido de la carpeta. Vuelve a abrir Teams. No se pierden chats ni archivos, porque están en la nube.
5. Reinicia el equipo. Si el código sigue apareciendo, registra un ticket para APLICACIONES con el código completo, la hora y el modelo de la cámara.

## Pantalla compartida: no se ve, sale en negro o el público ve otra ventana

Síntomas habituales: "cuando comparto pantalla, los demás ven negro", "no me deja compartir", "comparto una ventana y se ve otra cosa", "al compartir el monitor se ve mal".

1. En la reunión, haz clic en "Compartir" y elige "Pantalla" o "Ventana" con cuidado. Si eliges la pantalla completa, todo lo que aparezca en ella será visible para los participantes.
2. Si la ventana aparece en negro, es probable que la aplicación use aceleración de hardware. Minimiza la ventana y vuelve a compartirla, o usa "Compartir pantalla" en lugar de una ventana.
3. Si no te deja compartir, revisa que no haya otra persona compartiendo en la misma reunión. Solo una persona puede compartir a la vez; pide a esa persona que deje de compartir.
4. Si el monitor externo no aparece, presiona Windows + P y elige "Extender" para que el sistema reconozca el monitor. Luego vuelve a compartir.
5. Antes de compartir, cierra las notificaciones y los documentos con información confidencial que no deban verse.

## No puedo iniciar sesión en la reunión o en la aplicación

Síntomas habituales: "me pide la contraseña cada vez", "dice que mi cuenta no tiene licencia", "no me deja entrar a la reunión con mi correo", "aparece un error de inicio de sesión".

1. Inicia sesión siempre con tu cuenta corporativa completa. Las cuentas personales no tienen acceso a las reuniones de la empresa.
2. Si la aplicación pide la contraseña una y otra vez, cierra la sesión, reinicia la aplicación y vuelve a iniciar sesión. Si pide la verificación en dos pasos, aprueba la solicitud en Microsoft Authenticator.
3. Si la cuenta aparece como bloqueada, espera 15 minutos antes de intentar de nuevo. Consulta el manual de cuentas y correo.
4. Si el mensaje dice que la licencia no está disponible, registra un ticket para APLICACIONES. No compres licencias por tu cuenta.
5. Para una reunión con cliente, revisa que el enlace de invitación sea el que recibiste de la persona organizadora. No abras enlaces de reuniones que llegaron por correo sin que las hayas solicitado; repórtalos como correo sospechoso.

## Mala calidad de video o audio entrecortado

Síntomas habituales: "la video llamada se congela", "se me ve pixelada", "la voz se escucha entrecortada", "la reunión se corta cada rato".

1. Acércate al router Wi-Fi o conecta la laptop por cable de red.
2. Cierra las aplicaciones que consuman red: descargas, sincronizaciones de OneDrive, actualizaciones de Windows y videos en el navegador.
3. Apaga el video si no es necesario. El audio consume muy poca red, y la reunión funciona mejor con el video desactivado.
4. En la aplicación, baja la calidad del video o desactiva el fondo virtual. Los fondos borrosos o de imagen consumen más procesador.
5. Cierra otros programas que usen mucho procesador. Revisa el Administrador de tareas (Ctrl + Shift + Esc) antes de la reunión.
6. Si la calidad es mala en todas las reuniones y en todas las redes, registra un ticket para REDES con la hora y el lugar donde ocurre.

## Google Meet o Zoom en reuniones con clientes

Algunos clientes o proveedores piden Zoom o Google Meet. Usa la aplicación que indique la invitación. Si no está instalada, solicítala por el Portal de aplicaciones. Si la aplicación pide actualizarse, hazlo desde el propio programa antes de la reunión.

Si la reunión pide permisos de cámara o micrófono y no los recibes, sigue los pasos de cámara y micrófono de este manual. Si la aplicación no abre o se cierra al unirse, usa el manual de software.

## Cuándo registrar el ticket

Registra el ticket si la cámara o el micrófono no funcionan después de seguir este manual, si el error caa70004 vuelve a aparecer después de reiniciar, si no puedes iniciar sesión por una causa que no aparece aquí o si la calidad de la reunión es mala en todas las redes. Indica la aplicación, la versión, el código de error completo, la hora y el modelo del equipo y de la cámara o los auriculares.
