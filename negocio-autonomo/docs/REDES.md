# Conectar redes sociales

El sistema publica **solo borradores que hayas aprobado**, **solo cuando pulses «Publicar»** en
**Contenido**, como mucho 2 al día por red (`social_daily_limit`), y nunca lee mensajes ni comenta.
Los permisos van en tu `.env`. **No los pegues en ningún chat.**

| Red | Estado | Coste |
|---|---|---|
| LinkedIn | Conector listo | Gratis |
| Instagram | Pendiente | Gratis |
| Facebook | Pendiente (requiere revisión de Meta) | Gratis |
| TikTok | Pendiente (requiere auditoría de TikTok) | Gratis |
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
