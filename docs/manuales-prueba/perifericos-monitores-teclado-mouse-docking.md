# Periféricos: monitor sin señal, segundo monitor, teclado, mouse, docking, USB, audio y webcam

Empresa Demo S.A.C. — Mesa de Ayuda de TI. Versión 1.0, noviembre de 2026.

Este manual resuelve los problemas con los periféricos que usan los colaboradores en su puesto de trabajo: el monitor no muestra imagen, el segundo monitor no aparece, el teclado o el mouse no responden, la estación de acoplamiento (docking) no funciona, un USB no es reconocido, el audio no suena o la webcam no aparece. Antes de empezar, anota el modelo del periférico y el puerto donde está conectado.

## El monitor dice "Sin señal"

Síntomas habituales: "el monitor se prende pero dice Sin señal", "la pantalla del monitor está negra", "el monitor no muestra nada aunque la laptop funciona", "el monitor parpadea".

1. Revisa que el cable de video (HDMI, DisplayPort o USB-C) esté conectado en ambos extremos. Desconéctalo y vuelve a conectarlo hasta que quede firme.
2. Usa el botón de entrada o "Input" del monitor y elige la entrada donde conectaste el cable. Muchos monitores tienen dos o tres entradas y muestran "Sin señal" cuando la entrada no es la correcta.
3. Revisa que el monitor esté encendido y que el cable de corriente esté conectado al tomacorriente o a la regleta.
4. Presiona Windows + P en la laptop y elige "Extender" o "Duplicar". Si no pasa nada, reinicia el equipo con el cable ya conectado.
5. Si el monitor se conecta a una estación de acoplamiento, prueba conectando el cable directamente a la laptop. Si funciona, el problema está en el docking.
6. Si ningún cable ni entrada funcionan, prueba el monitor con otro equipo. Si tampoco muestra imagen, registra un ticket para INFRAESTRUCTURA para reemplazo. Si funciona con otro equipo, el problema está en la laptop o en el puerto de video.

## Quiero usar un segundo monitor o extender la pantalla

Síntomas habituales: "necesito dos pantallas para trabajar", "el segundo monitor no aparece", "Windows solo muestra un monitor", "el monitor aparece pero la resolución está mal".

1. Conecta el monitor y presiona Windows + P. Elige "Extender" para usar las dos pantallas como una sola superficie de trabajo.
2. Si el monitor no aparece, abre Configuración, Sistema, Pantalla, y haz clic en "Detectar". Si aún no aparece, usa "Identificar" para confirmar cuál es cada pantalla.
3. Para cambiar la resolución, ve a Configuración, Sistema, Pantalla, Resolución de pantalla, y elige la recomendada, que aparece con la marca "(recomendada)".
4. Si el texto se ve muy pequeño o muy grande, ajusta la escala en Configuración, Sistema, Pantalla, Escala. Usa el 100 % o el 125 % según el monitor.
5. Para ubicar las pantallas, arrastra los rectángulos en Configuración, Sistema, Pantalla, hasta que coincidan con su posición física.
6. Si el segundo monitor parpadea o se apaga de forma aleatoria, revisa el cable y el puerto. Un cable de video suelto es la causa más común.

## Teclado o mouse que no responden

Síntomas habituales: "el teclado no escribe", "el mouse se mueve a saltos", "el mouse inalámbrico no funciona", "el teclado escribe otras letras", "el teclado Bluetooth ya no se conecta".

Para equipos con cable:

1. Desconecta el cable y vuelve a conectarlo en otro puerto USB del equipo.
2. Si el teclado escribe letras diferentes, revisa el idioma del teclado. Presiona Windows + Espacio para cambiar entre Español (Perú) y el idioma que estés usando.
3. Si el teclado no responde después de reiniciar, revisa en el Administrador de dispositivos (Windows + X, luego Administrador de dispositivos) si aparece con un signo de advertencia.

Para equipos inalámbricos:

1. Revisa las pilas o la carga de la batería. Muchos mouse y teclados se apagan sin avisar.
2. Confirma que el receptor USB esté conectado directamente al equipo, no a un concentrador ni a un docking, porque algunos bloquean la señal.
3. Si usa Bluetooth, abre Configuración, Bluetooth y dispositivos, y elige "Quitar" el dispositivo. Luego usa "Agregar dispositivo" para emparejarlo de nuevo.
4. Si el mouse se mueve a saltos, cambia la superficie de apoyo y aleja otros receptores inalámbricos del equipo.

## Estación de acoplamiento (docking) que no funciona

Síntomas habituales: "al conectar la laptop al docking no pasa nada", "el docking no carga la laptop", "no tengo internet cuando estoy en el docking", "los monitores se apagan al conectarlo".

1. Desconecta la laptop del docking, espera diez segundos y vuelve a conectarla. Usa el cable USB-C o Thunderbolt que vino con el docking.
2. Revisa que el docking tenga corriente. Muchos docking muestran una luz de encendido cuando reciben energía.
3. Conecta la laptop directamente al tomacorriente, no a una regleta sin protección. Algunos docking no cargan la laptop si la fuente de poder no está conectada.
4. Si los monitores no se encienden, revisa que cada cable de video esté conectado al docking y que el monitor tenga la entrada correcta.
5. Si el Ethernet no funciona, sigue el manual de red. Revisa que el cable de red esté en el puerto del docking, no en la laptop.
6. Reinicia la laptop con el docking conectado. Si después del reinicio sigue sin funcionar, registra un ticket para INFRAESTRUCTURA con el modelo del docking y el de la laptop.

## Un USB no es reconocido o aparece "Dispositivo USB no reconocido"

Síntomas habituales: "conecto la memoria y no aparece", "Windows dice Dispositivo USB no reconocido", "el administrador de dispositivos muestra un signo amarillo", "aparece el error con código 43".

1. Prueba con otro puerto USB y otro cable. Un cable que solo carga, sin datos, no muestra el dispositivo.
2. Desconecta todos los dispositivos USB, deja solo el que falla y reinicia el equipo.
3. Abre el Administrador de dispositivos, busca el dispositivo con un signo de advertencia y revisa el mensaje de estado. El código 43 indica que Windows detuvo el dispositivo porque informó un problema.
4. Haz clic derecho en el dispositivo y elige "Desinstalar dispositivo". Desconéctalo, vuelve a conectarlo y deja que Windows lo instale otra vez.
5. Si el problema es con un concentrador USB, desconecta el concentrador y conecta el dispositivo directo al equipo.
6. Si el equipo se apaga los puertos USB para ahorrar energía, abre Configuración de energía avanzada y desactiva "Configuración de suspensión selectiva de USB" en modo con batería y conectado.
7. Si el dispositivo es de la empresa y sigue sin funcionar, registra un ticket para INFRAESTRUCTURA. Por seguridad, no conectes memorias USB de origen desconocido.

## Audio: no suena, el micrófono no funciona o aparece "No hay dispositivos de salida de audio instalados"

Síntomas habituales: "no sale sonido de la laptop", "los audífonos no suenan", "el micrófono no capta mi voz", "dice que no hay dispositivos de audio instalados".

1. Revisa el volumen del equipo y que el ícono de sonido no esté silenciado.
2. Haz clic en el ícono de sonido de la barra de tareas y elige el dispositivo de salida correcto. Los audífonos USB o Bluetooth suelen aparecer con el nombre del fabricante.
3. Abre Configuración, Sistema, Sonido, y en Entrada revisa que el micrófono correcto esté seleccionado y que la barra de volumen se mueva al hablar.
4. Si aparece "No hay dispositivos de salida de audio instalados", abre el Administrador de dispositivos, expande Controladores de sonido, video y juegos, y verifica que no haya dispositivos con signo de advertencia. Desinstala y vuelve a conectar el dispositivo de audio.
5. Usa "Solucionar problemas" de audio desde Configuración, Sistema, Solucionar problemas.
6. Si el problema continúa con varios audífonos, registra un ticket para APLICACIONES o INFRAESTRUCTURA según el caso.

## Webcam que no aparece o sale en negro

Síntomas habituales: "la cámara no aparece en las reuniones", "la cámara sale negra", "dice que la cámara está en uso", "la webcam no se encuentra en Windows".

1. Revisa la tapa física de la cámara o el interruptor de privacidad si el equipo lo tiene.
2. Abre Configuración, Bluetooth y dispositivos, Cámaras, y confirma que la cámara aparezca y esté activada.
3. Abre Configuración, Privacidad y seguridad, Cámara, y revisa que el acceso a la cámara esté activado para las aplicaciones y para la aplicación de reuniones que usas.
4. Cierra todas las aplicaciones que puedan estar usando la cámara, como otra reunión o un programa de grabación.
5. En el Administrador de dispositivos, revisa la sección Cámaras. Si la cámara tiene un signo de advertencia, desinstálala y reinicia el equipo.
6. Si la cámara sigue sin aparecer, registra un ticket para INFRAESTRUCTURA. Para errores específicos de las aplicaciones de reunión, consulta el manual de videoconferencia.

## Cuándo registrar el ticket

Registra el ticket si el periférico sigue sin funcionar después de seguir este manual, si el equipo muestra un código de error en el Administrador de dispositivos, si el monitor o el docking no encienden o si varios colaboradores del mismo piso tienen el mismo problema. Indica el modelo del periférico, el puerto usado y el código de error que aparece en el Administrador de dispositivos.
