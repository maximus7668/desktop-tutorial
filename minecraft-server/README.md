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

## Ponerlo en marcha

Necesitas un ordenador o VPS encendido 24/7 con [Docker](https://docs.docker.com/get-docker/)
(4 GB de RAM libres como mínimo).

```bash
cd minecraft-server
cp .env.example .env      # y edita los nombres
docker compose up -d
docker compose logs -f    # espera a ver "Done" y "Started Geyser"
```

### Abrir puertos en el router

Redirige hacia la IP del ordenador del servidor:

- `25565` **TCP** → jugadores de PC
- `19132` **UDP** → jugadores de consola

Si usas un VPS (Oracle Cloud gratis, Hetzner, etc.), abre los mismos puertos en su firewall.

## Cómo entra cada uno

### PC (Java)
Multijugador → Añadir servidor → `TU_IP` (o tu dominio).

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
   pon DNS primario `104.238.130.180` (BedrockConnect). Al pulsar en
   cualquier servidor destacado se abre un menú donde escribes `TU_IP` y
   puerto `19132`.

### Móvil / Windows Bedrock
Servidores → Añadir servidor → `TU_IP`, puerto `19132`.

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
