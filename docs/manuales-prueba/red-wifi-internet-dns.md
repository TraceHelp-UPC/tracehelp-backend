# Red: Wi-Fi conectado pero sin internet, error de DNS y cable de red

Empresa Demo S.A.C. — Mesa de Ayuda de TI. Versión 1.0, noviembre de 2026.

Este manual cubre los incidentes de conectividad más frecuentes en los equipos de la empresa: el Wi-Fi aparece conectado pero no abre páginas, el navegador muestra errores de DNS, el equipo tiene una IP que empieza por 169.254, el cable de red no funciona, un portal de inicio de sesión no aparece o la configuración de proxy bloquea las páginas. Los comandos se ejecutan en el Símbolo del sistema o en PowerShell. Si no sabes abrirlos, pide ayuda al analista en lugar de ejecutar comandos desconocidos.

## Tengo Wi-Fi pero no tengo internet

Síntomas habituales: "dice conectado pero no abre nada", "el Wi-Fi tiene barritas pero no carga la página", "WhatsApp y Teams no conectan", "el internet funciona en el celular y en la laptop no".

1. Confirma que el problema es del equipo y no de la red. Mira si otros colaboradores de tu área también pierden la conexión. Si sí, es un problema de la red del área: registra el ticket como REDES con prioridad alta.
2. Desactiva y vuelve a activar el Wi-Fi con el icono de red de la barra de tareas, o usa Windows + A y el botón Wi-Fi.
3. Abre el Símbolo del sistema y ejecuta `ipconfig /all`. Revisa la línea "Puerta de enlace predeterminada" y la dirección IPv4. Si la dirección empieza por 169.254, consulta la sección de IP 169.254 más abajo.
4. Ejecuta `ping` contra la puerta de enlace que mostró el paso anterior, por ejemplo `ping 192.168.1.1`. Si responde, el problema está fuera del equipo, en el router o en el proveedor. Si no responde, reinicia el Wi-Fi del equipo y vuelve a intentarlo.
5. Ejecuta `ping 8.8.8.8`. Si responde pero las páginas no abren, el problema es el DNS: sigue la sección siguiente.
6. Si el Wi-Fi sigue sin navegar, olvida la red y vuelve a conectarte. En Configuración, Red e Internet, Wi-Fi, Administrar redes conocidas, elige la red y pulsa "Olvidar". Luego conéctate otra vez escribiendo la clave del Wi-Fi de la oficina.

## Error DNS_PROBE_FINISHED_NO_INTERNET o ERR_NAME_NOT_RESOLVED

Síntomas habituales: "el navegador dice que no hay internet pero el Wi-Fi está conectado", "aparece DNS_PROBE_FINISHED_NO_INTERNET", "dice que no se puede acceder al sitio porque no se encontró la dirección del servidor", "aparece ERR_NAME_NOT_RESOLVED".

Estos mensajes significan que el equipo no puede traducir el nombre de la página a una dirección. La conexión puede estar bien; falla la consulta DNS.

1. Abre el Símbolo del sistema como usuario normal y ejecuta `ipconfig /flushdns`. El sistema responde "Se vació correctamente la caché de resolución de DNS".
2. Ejecuta `ipconfig /release` y luego `ipconfig /renew`. Espera a que termine cada comando. La primera instrucción libera la dirección y la segunda pide una nueva al servidor DHCP.
3. Prueba la consulta con `nslookup www.office.com`. Si responde con una dirección IP, el DNS funciona y el problema estaba en la caché del navegador. Cierra el navegador por completo y vuelve a abrirlo.
4. Si `nslookup` no responde o da un error de tiempo agotado, abre Configuración, Red e Internet, Wi-Fi o Ethernet, y revisa los servidores DNS. Deben ser los que asigna la red de la empresa. No cambies los DNS a servidores públicos sin autorización, porque las páginas internas dejarían de abrir.
5. Cierra el navegador y prueba en otra aplicación. Si Teams o Outlook funcionan, el problema es la configuración del navegador: revisa la sección de proxy.

## IP que empieza por 169.254 (sin acceso a la red)

Síntomas habituales: "me sale un signo de exclamación en el Wi-Fi", "dice Sin acceso a Internet", "ipconfig muestra 169.254.x.x", "la red aparece pero no me deja hacer nada".

Cuando el equipo no recibe una dirección del servidor DHCP de la red, Windows asigna una dirección automática que empieza por 169.254. Con esa dirección el equipo solo ve a otros equipos de su mismo segmento, pero no sale a internet ni a los sistemas de la empresa.

1. Ejecuta `ipconfig /release` y después `ipconfig /renew`. Si la dirección cambia a una del rango de la red, el problema estaba resuelto.
2. Desconecta el cable de red o el Wi-Fi, espera diez segundos y vuelve a conectarlo.
3. Reinicia el equipo. En muchos casos el servicio de red se recupera después de un reinicio.
4. Si el problema continúa, abre Configuración, Red e Internet, Estado y ejecuta "Solucionar problemas de red". Registra el ticket para REDES con la salida de `ipconfig /all`.

Si el problema afecta a un solo equipo, la causa suele ser el adaptador. Si afecta a varios equipos a la vez, la causa suele ser el servidor DHCP o el switch del piso.

## Cable de red (Ethernet) sin conexión

Síntomas habituales: "el cable está conectado pero no tengo red", "la luz del puerto no prende", "en la laptop aparece Red no identificada", "con el docking no sale internet".

1. Revisa que el cable esté completamente insertado en el equipo y en la toma de pared o en el docking. Escucha el clic de la pestaña.
2. Observa la luz del puerto del equipo. Si no hay luz, prueba con otro cable que sepas que funciona. Un cable dañado es la causa más común.
3. Si usas un docking, desconéctalo y vuelve a conectarlo. Después de conectar el equipo al docking, espera unos segundos antes de revisar la red.
4. Abre Configuración, Red e Internet, Ethernet, y confirma que el adaptador esté activado. Si aparece "Deshabilitado", actívalo.
5. Si el cable y el puerto funcionan en otro equipo, el problema es del controlador de red. Reinicia el equipo. Si persiste, registra un ticket para REDES indicando el modelo del equipo.

## Portal cautivo: la red pide iniciar sesión en el navegador

Síntomas habituales: "al conectarme me abre una página que pide usuario", "el Wi-Fi de visitantes no me deja navegar", "la página de la red no carga".

Algunas redes de la empresa, como la red de visitantes, muestran un portal de inicio de sesión antes de dar acceso a internet. Si el navegador no abre esa página, sigue estos pasos:

1. Abre una ventana privada del navegador y escribe una dirección web que empiece por "http" (sin la "s"), por ejemplo una página de prueba de la mesa de ayuda. Esa página redirige al portal de inicio de sesión.
2. Si no abre, desconéctate y vuelve a conectarte a la red.
3. Para la red de colaboradores, no uses el portal de visitantes. Inicia sesión con tu cuenta corporativa en la red de empresa. Si no te aparece, revisa que no tengas una conexión guardada a otra red.

## Configuración de proxy que bloquea las páginas

Síntomas habituales: "solo algunas páginas abren", "aparece Error de proxy", "ERR_PROXY_CONNECTION_FAILED", "en casa no abre nada pero en la oficina sí".

1. Abre Configuración, Red e Internet, Proxy. Si "Usar un servidor proxy" está activado y no lo activaste tú, desactívalo.
2. Si el equipo debe usar proxy por política de la empresa, no cambies la configuración. Registra un ticket para REDES.
3. Si el proxy aparece configurado con una dirección que no reconoces, no la modifiques. Escala el caso a SEGURIDAD, porque puede ser un cambio no autorizado.
4. Después de cambiar la configuración, cierra el navegador por completo y vuelve a abrirlo.

## Cuándo registrar el ticket

Registra el ticket si la red no se recupera después de seguir este manual, si varias personas del área pierden internet al mismo tiempo, si aparece una dirección 169.254 que se repite o si el proxy está configurado de una forma que no reconoces. Adjunta la salida de `ipconfig /all`, el nombre de la red (no la clave) y el mensaje exacto del navegador.
