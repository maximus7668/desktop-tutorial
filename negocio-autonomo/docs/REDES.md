# Conectar redes sociales

El sistema publica **solo borradores que hayas aprobado**, **solo cuando pulses «Publicar»** en
**Contenido**, como mucho 2 al día por red (`social_daily_limit`), y nunca lee mensajes ni comenta.
Los permisos van en tu `.env`. **No los pegues en ningún chat.**

| Red | Estado | Coste |
|---|---|---|
| LinkedIn | Conector listo | Gratis |
| Instagram (cuenta profesional) | Conector listo (carruseles) | Gratis |
| Facebook | Pendiente (requiere revisión de Meta) | Gratis |
| TikTok | Pendiente: sin auditoría de TikTok solo publica en privado; de momento, a mano | Gratis |
| X | Pendiente (de pago) | ~0,20 $ por publicación con enlace |

## LinkedIn (perfil personal)

### Paso 1. Crear la app (5 min)

1. Entra en https://www.linkedin.com/developers/apps/new con tu cuenta.
2. Rellena:
   - **App name:** por ejemplo «Negocio supervisado».
   - **LinkedIn Page:** LinkedIn exige asociar la app a una página de empresa. Si no tienes, usa el enlace
     «Create a new LinkedIn Page» y crea una sencilla (gratis); puedes dejarla casi vacía.
   - **Privacy policy URL:** opcional. Si te la pide, puedes poner la de tu página de privacidad cuando la tengas en internet.
   - **App logo:** cualquier imagen cuadrada.
3. Acepta las condiciones y pulsa **Create app**.
4. Si en la pestaña **Settings** aparece la asociación con la página como «no verificada», pulsa **Verify** y
   abre el enlace que te da (como administrador de la página, la apruebas tú mismo).

### Paso 2. Activar los dos productos (2 min)

En la pestaña **Products** de tu app, pulsa **Request access** en:
- **Share on LinkedIn** (permite publicar en tu perfil: permiso `w_member_social`).
- **Sign In with LinkedIn using OpenID Connect** (permite saber qué cuenta eres: `openid`, `profile`).

Ambos son de alta inmediata. Comprueba en **Auth → OAuth 2.0 scopes** que aparecen `openid`, `profile` y `w_member_social`.

### Paso 3. Generar el permiso (token) (2 min)

1. Abre el generador de tokens: https://www.linkedin.com/developers/tools/oauth/token-generator
2. Elige tu app, marca **openid**, **profile** y **w_member_social** y pulsa **Request access token**.
3. LinkedIn te pide permiso en una ventana: acepta.
4. Copia el **token** (texto largo) y fíjate en cuándo caduca (normalmente **60 días**).

### Paso 4. Ponerlo en el sistema (en tu PC)

En `negocio-autonomo\.env` (con el Bloc de notas):

```
LINKEDIN_ACCESS_TOKEN=pega-aquí-el-token
LINKEDIN_TOKEN_EXPIRES=AAAA-MM-DD
```

(La fecha de caducidad sirve para que el panel te avise 7 días antes.) Cierra y vuelve a abrir `iniciar-windows.bat`.

### Paso 5. Probar sin publicar nada

```powershell
.venv\Scripts\python -m app.cli social-test linkedin
```

Debe decir `OK: conectado como <tu nombre>`. Si dice 401, el token no vale o caducó; si dice 403, falta algún producto o scope.

### Paso 6. Usarlo

**Contenido** → aprueba el borrador de LinkedIn → botón **«Publicar en linkedin ahora»**. Se publica en
público con tu cuenta y queda el enlace a la publicación. Antes, asegúrate de que `PUBLIC_BASE_URL` es tu
dirección https de cloudflared (si no, el sistema se niega a publicar porque el enlace no funcionaría).

### Retirar el permiso

En LinkedIn: **Ajustes → Privacidad de datos → Servicios y apps permitidos** → elimina la app. Al momento
el sistema deja de poder publicar.

## Instagram (cuenta profesional)

Usa la **API de Instagram con inicio de sesión de Instagram**: no hace falta página de Facebook. Instagram
solo publica con imagen, así que el sistema convierte el borrador en un **carrusel** (una imagen por cada
«1/, 2/…» del texto) y el «Pie de foto» va debajo. Las imágenes se sirven en `https://TU_DOMINIO/media/ig/...`
solo cuando has aprobado el borrador, porque Instagram las descarga de ahí.

### Paso 1. Crear la app en Meta (10 min)

1. Entra en https://developers.facebook.com con tu cuenta de Facebook (si es la primera vez, pulsa
   **Empezar** y verifica tu teléfono: es el registro de desarrollador, gratis).
2. **Mis apps → Crear app**. Nombre: por ejemplo «Negocio supervisado». En «Caso de uso» elige
   **Administrar mensajes y contenido en Instagram** (o «Otro» → tipo **Empresa**, si no aparece).
3. Dentro de la app, en el menú de la izquierda: **Instagram → Configuración de la API con inicio de sesión
   de Instagram**.

### Paso 2. Generar el token (5 min)

1. En esa pantalla, apartado **Generar identificadores de acceso**, pulsa **Añadir cuenta** e inicia sesión
   con tu cuenta **profesional** de Instagram. Acepta los permisos (`instagram_business_basic` e
   `instagram_business_content_publish`).
2. Si te dice que la cuenta no tiene un rol en la app: **Roles de la app → Roles → Añadir personas →
   Evaluador de Instagram** con tu usuario de Instagram. Acepta la invitación en la app de Instagram
   (**Configuración → Permisos del sitio web → Apps y sitios web → Invitaciones de evaluador**) y repite el punto 1.
3. Pulsa **Generar token** junto a tu cuenta, copia el texto largo y apunta la fecha: caduca a los **60 días**.

La app puede quedarse en **modo de desarrollo**: así puede publicar en las cuentas que tienen un rol en ella
(la tuya), sin pasar la revisión de Meta.

### Paso 3. Ponerlo en el sistema

En `negocio-autonomo\.env`:

```
INSTAGRAM_ACCESS_TOKEN=pega-aquí-el-token
INSTAGRAM_TOKEN_EXPIRES=AAAA-MM-DD
```

Reinicia con `iniciar-windows.bat` y prueba sin publicar nada:

```powershell
.venv\Scripts\python -m app.cli social-test instagram
```

Debe decir `OK: conectado como <tu usuario>`.

### Paso 4. Usarlo

1. Pon en la **biografía** de Instagram el enlace de la página del producto (en los pies de foto los enlaces
   no se pueden pulsar; el borrador ya dice «enlace en la bio»).
2. **Contenido** → aprueba el borrador de Instagram → **«Publicar en instagram ahora»**.

Si falla con 400, suele ser que Instagram no pudo descargar las imágenes: comprueba que deika.eu está
encendido (ventanas del panel y del túnel abiertas).

### Retirar el permiso

En Instagram: **Configuración → Permisos del sitio web → Apps y sitios web** → elimina la app.