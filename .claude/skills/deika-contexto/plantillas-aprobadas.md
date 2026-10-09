# Plantillas aprobadas

Solo los textos que el dueño ha aprobado. Lo que no está aquí no se envía sin aprobación
(nivel ROJO). Variables entre `{{ }}`; el agente solo rellena variables, no reescribe el texto.

Formato de cada entrada:

```
## <id> · v<versión> · <fecha de aprobación>
- Canal: email | whatsapp | telegram | sms
- Uso: cuándo se envía
- Nivel: rojo | amarillo | verde
- Asunto (si es email):
- Texto:
  ...
```

---

Fuente: `automatizacion/plantillas/whatsapp-seguimiento.md` (repo Deika-panel). Aprobadas por el dueño
el 2026-10-09 («apruebo las 3 plantillas»).

## seguimiento-tras-demo · v1 · 2026-10-09
- Canal: WhatsApp (envío manual por el dueño desde su móvil; n8n prepara el enlace wa.me)
- Uso: Tras la demo con la recepcionista IA, si el lead se mostró interesado.
- Nivel: rojo (siempre lo envía una persona)
- Variables: {{negocio}}, {{nombre_dueno}}
- Texto:
  ```
  Hola, soy {{nombre_dueno}}, de DEIKA (Vitoria-Gasteiz). Pediste info en deika.eu para {{negocio}} y ya probaste nuestra recepcionista con IA por teléfono. ¿Te va bien una llamada corta conmigo para ver cómo ponerla en marcha? Dime día y hora. Si no te interesa, dímelo y no te molestamos más.
  ```

## no-contesto-demo · v1 · 2026-10-09
- Canal: WhatsApp (envío manual por el dueño desde su móvil; n8n prepara el enlace wa.me)
- Uso: Si el lead no contestó a la llamada de demo.
- Nivel: rojo (siempre lo envía una persona)
- Variables: {{negocio}}, {{nombre_dueno}}
- Texto:
  ```
  Hola, soy {{nombre_dueno}}, de DEIKA (Vitoria-Gasteiz). Pediste en deika.eu que te llamáramos para enseñarte la recepcionista con IA para {{negocio}}, pero no te hemos pillado. ¿Cuándo te viene bien? Si prefieres, llámame tú. Si no te interesa, dímelo y no te molestamos más.
  ```

## tras-llamada-dueno · v1 · 2026-10-09
- Canal: WhatsApp (envío manual por el dueño desde su móvil; n8n prepara el enlace wa.me)
- Uso: Después de que el dueño hablara con el lead y quedara pendiente decidir.
- Nivel: rojo (siempre lo envía una persona)
- Variables: {{negocio}}, {{nombre_dueno}}
- Texto:
  ```
  Hola, soy {{nombre_dueno}}, de DEIKA (Vitoria-Gasteiz). Te escribo tras hablar por teléfono sobre la recepcionista con IA para {{negocio}}, que pediste en deika.eu. Sin prisa: cuando quieras retomarlo, aquí estoy. Si no te interesa, dímelo y no te molestamos más.
  ```

