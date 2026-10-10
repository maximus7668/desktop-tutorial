# Servidor de Minecraft con Fabric

| Componente | Versión |
|---|---|
| Minecraft (servidor) | **1.21.11** |
| Fabric Loader | **0.19.5** |
| Fabric Installer | 1.1.2 |
| Java necesario | **21** (o superior) |

Modo supervivencia, dificultad normal, hasta 10 jugadores, cuentas oficiales (`online-mode=true`) y **lista blanca activada**.

---

## 1. Requisito: Java 21

En Windows, abre *Símbolo del sistema* o *PowerShell* y escribe:

```
java -version
```

Si no sale la versión 21 o superior, instala **Eclipse Temurin 21 (JRE o JDK)** desde https://adoptium.net/temurin/releases/?version=21.
En el instalador, marca **"Add to PATH"** y **"Set JAVA_HOME"**. Cierra la ventana y vuelve a comprobarlo.

## 2. Arrancar el servidor (un solo comando)

- **Windows:** doble clic en `start.bat`, o desde la consola dentro de esta carpeta: `start.bat`
- **Linux/macOS:** `./start.sh`

La **primera vez** el script descarga e instala Fabric y el servidor de Minecraft (unos 60 MB). Las siguientes veces arranca directamente.
Cuando en la consola aparezca `Done (...)! For help, type "help"`, el servidor ya está listo.

La primera vez, Windows puede preguntar si permite a Java usar la red: acepta al menos en **redes privadas**.

### Detenerlo

Escribe `stop` en la consola del servidor. El script avisa de que lo reiniciará en 10 segundos.
Pulsa **Ctrl+C** en esa cuenta atrás para salir del todo (en Windows, responde `S` a "¿Desea terminar el trabajo por lotes?").
Si el servidor se cae por un error, el script lo vuelve a arrancar solo.

### Memoria

Los scripts usan `-Xms2G -Xmx4G` (empieza con 2 GB y usa hasta 4 GB). El PC necesita al menos unos 6 GB de RAM libres.
Con muchos mods puedes subir `-Xmx4G` a `-Xmx6G` en `start.bat` / `start.sh`.

## 3. Añadir mods

1. Descarga mods **de Fabric** para **Minecraft 1.21.11** (por ejemplo, en https://modrinth.com filtrando por versión *1.21.11* y loader *Fabric*).
2. Casi todos necesitan **Fabric API**: descárgala también para 1.21.11.
3. Copia los `.jar` en la carpeta `mods/` (lee `mods/LEEME.txt`).
4. Reinicia el servidor.

Los mods que añaden contenido (bloques, objetos, mobs…) también los tiene que instalar **cada jugador** en su Minecraft, con Fabric y las mismas versiones.
Los mods solo de servidor (rendimiento, copias de seguridad, permisos…) no hacen falta en los jugadores.

Si el servidor no arranca tras añadir un mod, quítalo y mira el error en `logs/latest.log`.

## 4. Lista blanca (quién puede entrar)

La lista blanca está **activada** (`white-list=true` y `enforce-whitelist=true` en `server.properties`): solo entran los jugadores que añadas.
Escribe estos comandos en la **consola del servidor** (sin `/`):

| Acción | Comando |
|---|---|
| Añadir un jugador | `whitelist add NombreDelJugador` |
| Quitar un jugador | `whitelist remove NombreDelJugador` |
| Ver la lista | `whitelist list` |
| Recargar `whitelist.json` tras editarlo a mano | `whitelist reload` |
| Desactivar la lista (entra cualquiera) | `whitelist off` |
| Volver a activarla | `whitelist on` |

- Usa el nombre de la cuenta de Minecraft Java del jugador (las mayúsculas dan igual, pero la cuenta tiene que existir).
- Los jugadores añadidos se guardan en `whitelist.json`.
- Para darte permisos de administrador y usar los comandos desde el juego (con `/`): `op TuNombre`.

## 5. Copias de seguridad

Lo importante es:

- `world/` — el mundo (incluye el Nether y el End).
- `mods/` — los mods instalados.
- `server.properties`, `whitelist.json`, `ops.json` — la configuración.
- `config/` — la configuración de los mods, si alguno la crea (añádela a los comandos de abajo si existe).

**Forma segura:** detén el servidor con `stop` (y Ctrl+C) y copia esas carpetas y archivos a otro sitio (otro disco, un USB, la nube).

**En Windows, con PowerShell** dentro de esta carpeta (servidor detenido), crea un ZIP con la fecha:

```powershell
Compress-Archive -Path world, mods, server.properties, whitelist.json, ops.json -DestinationPath "backup-$(Get-Date -Format yyyy-MM-dd_HH-mm).zip"
```

**En Linux/macOS:**

```bash
tar czf "backup-$(date +%Y-%m-%d_%H-%M).tar.gz" world mods server.properties whitelist.json ops.json
```

**Sin parar el servidor:** en la consola escribe `save-off` y después `save-all`, haz la copia y escribe `save-on` al terminar.

**Restaurar:** con el servidor detenido, borra `world/` y `mods/` y pon en su lugar los de la copia.

## 6. Conectarse

En Minecraft Java 1.21.11 (con Fabric y los mismos mods si hacen falta): **Multijugador → Añadir servidor**.

| Quién | Dirección |
|---|---|
| Tú, en el mismo PC | `localhost` |
| Alguien en tu misma red (wifi/casa) | IP local del PC, por ejemplo `192.168.1.50` (en Windows: `ipconfig` → "Dirección IPv4") |
| Alguien desde Internet (router) | tu IP pública (https://ifconfig.me) — requiere abrir el puerto |
| Alguien desde Internet (playit.gg) | la dirección que te da playit.gg |

El puerto es el **25565**, el que usa Minecraft por defecto, así que no hace falta escribirlo.

### Para que entren desde Internet (elige una opción)

**Opción A — Abrir el puerto en el router**
1. Pon una IP local fija al PC del servidor (en el router, "reserva DHCP").
2. En el router, crea una regla de *reenvío de puertos* (*port forwarding*): puerto **25565 TCP** → IP local del PC.
3. Comprueba que el Firewall de Windows permite Java (o el puerto 25565 TCP) en la red.
4. Da a tus amigos tu IP pública. Si cambia a menudo, usa un DNS dinámico (No-IP, DuckDNS…).
5. No funciona si tu operador usa CG-NAT (pasa con algunas fibras y redes móviles): en ese caso usa la opción B.

**Opción B — Túnel con playit.gg (sin tocar el router)**
1. Crea una cuenta en https://playit.gg y descarga el programa para Windows.
2. Ábrelo en el PC del servidor y vincúlalo con tu cuenta.
3. Crea un túnel **Minecraft Java** apuntando a `127.0.0.1:25565`.
4. Da a tus amigos la dirección que te muestra playit.gg (algo como `nombre.joinmc.link`).
5. El programa de playit.gg tiene que estar abierto mientras juegan.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `start.bat` / `start.sh` | Arrancar el servidor (y la primera vez, instalarlo) |
| `server.properties` | Configuración del servidor |
| `eula.txt` | Aceptación del EULA de Minecraft (https://aka.ms/MinecraftEULA) |
| `whitelist.json` | Jugadores permitidos |
| `mods/` | Mods de Fabric |
| `world/`, `logs/`, `libraries/`, `server.jar`… | Se crean al arrancar; no se suben al repositorio |
