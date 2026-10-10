#!/usr/bin/env bash
# Arranca el servidor de Minecraft (Fabric) y lo reinicia si se cae.
# Uso: ./start.sh   (Ctrl+C durante la cuenta atras para salir del todo)

cd "$(dirname "$0")" || exit 1

MC_VERSION="1.21.11"
LOADER_VERSION="0.19.5"
INSTALLER_VERSION="1.1.2"
INSTALLER_SHA1="74685b5a0178c4dabd4be741a276d35c59b5ec96"

# Primera vez: si faltan los archivos del servidor, instala Fabric.
if [ ! -f fabric-server-launch.jar ] || [ ! -f server.jar ] || [ ! -d libraries ]; then
    echo "Instalando Fabric $LOADER_VERSION para Minecraft $MC_VERSION..."
    INSTALLER="fabric-installer-$INSTALLER_VERSION.jar"
    curl -fSL -o "$INSTALLER" \
        "https://maven.fabricmc.net/net/fabricmc/fabric-installer/$INSTALLER_VERSION/$INSTALLER" || exit 1
    if command -v sha1sum >/dev/null; then
        SUM=$(sha1sum "$INSTALLER" | cut -d' ' -f1)
    else
        SUM=$(shasum -a 1 "$INSTALLER" | cut -d' ' -f1)
    fi
    if [ "$SUM" != "$INSTALLER_SHA1" ]; then
        echo "ERROR: el instalador descargado no es el esperado (SHA1 $SUM)."
        rm -f "$INSTALLER"
        exit 1
    fi
    java -jar "$INSTALLER" server -mcversion "$MC_VERSION" -loader "$LOADER_VERSION" \
        -downloadMinecraft -dir . || exit 1
    rm -f "$INSTALLER"
fi

while true; do
    java -Xmx4G -Xms2G -jar fabric-server-launch.jar nogui
    echo "El servidor se ha detenido. Se reinicia en 10 segundos (Ctrl+C para salir)."
    sleep 10 || exit 0
done
