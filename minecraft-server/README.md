# Servidor de Minecraft crossplay (PC + PlayStation) con mods

Servidor **Java con Fabric** al que pueden entrar:

- **PC (Minecraft Java)** directamente.
- **PlayStation, Xbox, Switch, móvil y Windows Bedrock** gracias a
  [Geyser](https://geysermc.org) (traduce Bedrock ↔ Java) y
  [Floodgate](https://geysermc.org/wiki/floodgate/) (les deja entrar con su cuenta de Xbox, sin comprar Java).

## Qué mods trae

| Mod | Para qué |
|---|---|
| Fabric API | Base que necesitan los demás mods |
| Geyser + Floodgate | Que entren los de consola |
| Lithium + FerriteCore | Más rendimiento, menos RAM |
| Chunky | Pre-generar el mapa para que no dé tirones |
| Terralith | Cientos de biomas nuevos (funciona sin instalar nada en el cliente) |

> **Importante:** en PlayStation no se pueden instalar mods, así que **solo
> sirven mods de servidor** (rendimiento, generación de mundo, comandos,
> protecciones…). Mods que añaden bloques o mobs nuevos (Create, Mekanismo,
> etc.) obligan a instalarlos en el cliente y **dejan fuera a la consola**.
> Para añadir más, búscalos en [Modrinth](https://modrinth.com/mods?e=server)
> con el filtro "Server side" y pon su nombre en `MODRINTH_PROJECTS` del
> `docker-compose.yml`.

## Lo más fácil (Windows)

1. Instala [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Descarga [este ZIP](https://github.com/maximus7668/desktop-tutorial/archive/refs/heads/claude/minecraft-cross-platform-mods-gw5ath.zip), descomprímelo y entra en `minecraft-server`.
3. Doble clic en **`INICIAR.bat`**. La primera vez te abre el Bloc de notas para poner los nombres; guarda y cierra.
4. Para apagar: doble clic en **`APAGAR.bat`**.

## Cuánto cuesta: 0 €

Todo lo que usa este servidor es gratis: Minecraft server, Fabric, los mods,
Geyser, Floodgate, Docker, playit.gg, MCXboxBroadcast y BedrockConnect.
Elige **una** de estas tres formas de tenerlo encendido:

| Opción | Cuesta | Ventajas | Pegas |
|---|---|---|---|
| **A. Tu propio PC + playit.gg** (recomendada) | 0 € | Fácil, sin tocar el router, sin tarjeta | Solo funciona mientras tu PC está encendido |
| **B. Oracle Cloud "Always Free"** | 0 € | Encendido 24/7, 4 núcleos y 24 GB de RAM gratis | Piden tarjeta para verificar (no cobran) y el alta es más técnica |
| **C. Aternos** | 0 € | Sin instalar nada, desde la web | Cola de espera, se apaga solo si no hay nadie, menos mods |

### Opción A – Tu PC + playit.gg (gratis, sin abrir puertos)

1. Instala [Docker Desktop](https://www.docker.com/products/docker-desktop/) (gratis para uso personal).
   Necesitas unos 4 GB de RAM libres.
2. Crea una cuenta gratis en [playit.gg](https://playit.gg), pulsa **Add agent → Docker**
   y copia la **secret key** que te da.
3. En esta carpeta:
   ```bash
   cp .env.example .env      # edita nombres y pega la clave en PLAYIT_SECRET
   docker compose --profile playit up -d
   docker compose logs -f mc # espera a ver "Done" y "Started Geyser"
   ```
4. En la web de playit.gg crea dos túneles (los dos entran en el plan gratis):
   - **Minecraft Java** → dirección local `mc`, puerto `25565` → te da una dirección tipo `algo.gl.joinmc.link` (para PC).
   - **Minecraft Bedrock** → dirección local `mc`, puerto `19132` → te da una dirección y un puerto (para consola).

   Esas direcciones son las que pasas a tus amigos en lugar de tu IP. Así no
   hace falta abrir puertos en el router y tu IP de casa no se comparte.

### Opción B – Oracle Cloud Always Free (24/7 gratis)

1. Date de alta en [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/).
2. Crea una instancia **Ampere A1** (ARM) con Ubuntu: hasta 4 OCPU y 24 GB de RAM entran en lo gratuito.
3. En la *Security List* de la red abre `25565/TCP` y `19132/UDP`, y en la máquina:
   `sudo iptables -I INPUT -p tcp --dport 25565 -j ACCEPT && sudo iptables -I INPUT -p udp --dport 19132 -j ACCEPT`
4. Instala Docker (`curl -fsSL https://get.docker.com | sh`), copia esta carpeta y lanza
   `docker compose up -d` (sin el perfil de playit). Tus amigos usan la IP pública de la instancia.

> Si aparece "Out of capacity" al crear la instancia, prueba otra zona o
> vuelve a intentarlo más tarde: pasa a menudo con las máquinas gratis.

### Opción C – Aternos (sin instalar nada)

En [aternos.org](https://aternos.org): crea un servidor **Fabric**, en
*Mods* instala **Geyser** y **Floodgate** más los mods de la tabla de
arriba, y activa *Bedrock/Geyser* en Opciones. Aternos te da la dirección
para PC y para consola. Alguien tiene que pulsar **Iniciar** en la web
cada vez que queráis jugar.

### Lo que sí hay que tener

- **PC:** el Minecraft **Java** original (el servidor no puede saltarse eso).
- **PlayStation:** su Minecraft normal. Para jugar en servidores **no hace falta PlayStation Plus**, solo una cuenta de Microsoft gratuita.

## Cómo entra cada uno

### PC (Java)
Multijugador → Añadir servidor → la dirección de Java de playit.gg (o la IP del servidor).

### PlayStation (y Xbox / Switch)
La consola **no deja escribir la IP de un servidor**, solo muestra los
servidores oficiales. Hay dos formas de saltarlo:

1. **Unirse por amigos (la más fácil)** – instala la extensión
   [MCXboxBroadcast](https://github.com/MCXboxBroadcast/Broadcaster/releases):
   descarga `MCXboxBroadcastExtension.jar`, ponlo en
   `data/config/Geyser-Fabric/extensions/` y reinicia
   (`docker compose restart`). En los logs saldrá un código para iniciar
   sesión con una **cuenta de Microsoft secundaria**. Los jugadores de PS
   añaden esa cuenta como amigo y el servidor aparece en la pestaña
   **Amigos** → Unirse.
2. **Cambiar el DNS de la PS** – en Ajustes → Red → configuración manual,
   pon DNS primario `104.238.130.180` (BedrockConnect, gratis). Al pulsar en
   cualquier servidor destacado se abre un menú donde escribes la dirección
   y el puerto de Bedrock (los de playit.gg, o la IP y `19132`).

### Móvil / Windows Bedrock
Servidores → Añadir servidor → dirección y puerto de Bedrock (playit.gg) o la IP y `19132`.

## Lista blanca y administradores

Está activada la lista blanca. Desde la consola del servidor:

```bash
docker exec -i mc-crossplay rcon-cli
whitelist add NombreJava
fwhitelist add GamertagPS      # jugadores de consola (comando de Floodgate)
op NombreJava
```

Los jugadores de consola aparecen dentro del juego con un `.` delante del nombre.

## Mantenimiento

```bash
docker compose pull && docker compose up -d   # actualizar servidor y mods
docker compose stop                           # apagar
```

Copia de seguridad: guarda la carpeta `data/` (ahí están el mundo y la configuración).
Pre-generar el mapa (recomendado la primera vez): `chunky radius 3000` y `chunky start` en la consola.
