# Puesta en marcha en Windows (0 €)

Tiempo: unos 30 minutos la primera vez. No hace falta pagar nada.
Nota honesta: estos pasos no se han podido probar en un Windows real (el sistema se desarrolló en Linux).
Si algún paso falla, copia el mensaje de error y pásamelo.

## 1. Instalar Python y Git

Abre **PowerShell** (tecla Windows → escribe «PowerShell» → Enter) y ejecuta:

```powershell
winget install -e --id Python.Python.3.13
winget install -e --id Git.Git
winget install -e --id Cloudflare.cloudflared
```

Cierra PowerShell y ábrelo de nuevo para que reconozca los programas. Comprueba:

```powershell
py --version
git --version
cloudflared --version
```

Si `winget` no existe: instala Python desde https://www.python.org/downloads/ (marca **«Add python.exe to PATH»**)
y Git desde https://git-scm.com/download/win.

## 2. Descargar el código

```powershell
cd $HOME\Documents
git clone -b claude/negocio-autonomo-mvp https://github.com/maximus7668/desktop-tutorial.git
cd desktop-tutorial\negocio-autonomo
```

Si el repositorio es privado, Git abrirá el navegador para que inicies sesión en GitHub.

## 3. Instalar dependencias

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## 4. Configurar `.env`

```powershell
copy .env.example .env
.venv\Scripts\python -c "import secrets;print(secrets.token_urlsafe(48))"
notepad .env
```

En el Bloc de notas cambia estas líneas (el resto se queda igual) y guarda:

```
APP_ENV=production
SECRET_KEY=pega aquí el texto largo que salió en el comando anterior
INITIAL_CAPITAL_EUR=0
OWNER_LEGAL_NAME=Nombre y apellidos completos
OWNER_TAX_ID=tu NIF
OWNER_ADDRESS=Calle, número, código postal, localidad
OWNER_CONTACT_EMAIL=tu email
```

`.env` no se sube nunca a GitHub. No pegues su contenido en chats.

## 5. Crear la base de datos y tu usuario

```powershell
.venv\Scripts\python -m app.cli init
.venv\Scripts\python -m app.cli create-admin alejandro
.venv\Scripts\python -m app.cli import-research examples\investigacion_2026-10-20.json
```

`create-admin` te pide una contraseña (mínimo 12 caracteres; no se ve mientras escribes).

## 6. Arrancar

Haz doble clic en **`iniciar-windows.bat`** (carpeta `negocio-autonomo`). Se abren dos ventanas negras:
«Panel» y «Trabajador». **No las cierres**: mientras estén abiertas, el sistema funciona.

Abre el navegador en http://127.0.0.1:8000 y entra con tu usuario.

## 7. Primeros pasos en el panel

1. **Ajustes → Cumplimiento**: lee `Aviso legal` y `Privacidad` (enlaces al pie de cualquier página) y marca
   como hechos los 4 puntos «publish».
2. **Tareas → director.cycle → Encolar**. En unos segundos aparecerá un experimento en **Aprobaciones**.
3. Apruébalo. El constructor crea la página y te pide aprobar su publicación: apruébala.
4. **Productos → vista previa** para verla.

## 8. Hacerla visible en Internet (gratis)

Abre otra ventana de PowerShell y ejecuta:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Saldrá una dirección como `https://palabras-al-azar.trycloudflare.com`. Tu página estará en
`https://palabras-al-azar.trycloudflare.com/p/<slug>` (el slug está en **Productos**).

Ten en cuenta:
- Esa dirección **cambia cada vez** que reinicias cloudflared, y Cloudflare la ofrece para pruebas, sin garantías.
  Para una dirección fija hace falta un dominio propio (~10-15 €/año), cuando haya capital.
- La dirección también da acceso a la pantalla de login del panel. Está protegida con contraseña y límite de
  intentos, pero usa una contraseña fuerte.
- Comparte el enlace de la página donde esté tu público (grupos, foros, contactos). Esas visitas sí cuentan
  como **reales**.

## 9. Día a día

- El ordenador tiene que estar encendido y sin suspender (Configuración → Sistema → Energía → «Nunca» al
  estar enchufado), con las tres ventanas abiertas (Panel, Trabajador, cloudflared).
- Copias: el sistema guarda una al día en `backups\`. Cópiala de vez en cuando a OneDrive o a un USB.
- Parar todo de golpe: botón rojo del panel, o `.venv\Scripts\python -m app.cli stop "motivo"`.
- Apagar: cierra las ventanas. Al volver a abrir `iniciar-windows.bat`, continúa donde estaba.
- Aportar dinero el mes que viene: **Finanzas → Aportar capital**.

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `py` no se reconoce | Reinstala Python marcando «Add python.exe to PATH» y abre una PowerShell nueva |
| «SECRET_KEY debe tener al menos 32 caracteres» | Revisa la línea `SECRET_KEY=` de `.env` |
| El login no funciona en http://127.0.0.1:8000 | Con `APP_ENV=production` la cookie es segura: entra por la dirección https de cloudflared |
| Windows Defender pregunta por el firewall | Puedes denegar el acceso a redes: el panel solo escucha en tu propio equipo |
| La página da 404 | Aún no está publicada: revisa **Aprobaciones** |
