class_name Personajes
extends RefCounted

## Ficha de cada luchador. Los mismos id que en el juego.toml de la fábrica,
## para que sus modelos, voces y animaciones lleguen solos.

static func ids() -> PackedStringArray:
	return PackedStringArray(["ren", "yuki"])


static func datos(id: String) -> Dictionary:
	match id:
		"ren":
			return {
				"id": "ren",
				"nombre": "Ren Kagura",
				"apodo": "El Puño Carmesí",
				"estilo": "Equilibrado · fuego",
				"vida": 3000.0,
				"velocidad": 15.0,
				"fuerza": 1.0,
				"defensa": 1.0,
				"pelo": "puntas",
				"accesorio": "cinta",
				"mangas": "cortas",
				"colores": {
					"piel": Color(0.96, 0.78, 0.64),
					"pelo": Color(0.13, 0.09, 0.17),
					"punta": Color(0.95, 0.24, 0.14),
					"arriba": Color(1.0, 0.45, 0.2),
					"ribete": Color(1.0, 0.82, 0.25),
					"abajo": Color(0.18, 0.16, 0.29),
					"botas": Color(0.11, 0.09, 0.15),
					"manos": Color(0.96, 0.94, 0.88),
					"ojos": Color(0.95, 0.62, 0.1),
					"cinta": Color(0.97, 0.95, 0.9),
					"ki": Color(1.0, 0.48, 0.12),
					"ki_nucleo": Color(1.0, 0.95, 0.72),
				},
				"super": {"nombre": "Guren Bakuha", "dano": 760.0},
				"frases": {
					"entrada": "¡Vamos allá! ¡Enséñame todo lo que tienes!",
					"tecnica": "¡Guren... Bakuha!",
					"victoria": "Mientras arda este puño, no pienso caer.",
					"derrota": "Todavía... no he terminado...",
				},
			}
		"yuki":
			return {
				"id": "yuki",
				"nombre": "Yuki Shirane",
				"apodo": "La Dama del Hielo",
				"estilo": "Rápida · hielo",
				"vida": 2800.0,
				"velocidad": 16.5,
				"fuerza": 0.95,
				"defensa": 0.95,
				"pelo": "coleta",
				"accesorio": "",
				"mangas": "largas",
				"colores": {
					"piel": Color(0.98, 0.86, 0.77),
					"pelo": Color(0.9, 0.94, 1.0),
					"punta": Color(0.48, 0.85, 1.0),
					"arriba": Color(0.16, 0.25, 0.52),
					"ribete": Color(0.37, 0.85, 1.0),
					"abajo": Color(0.11, 0.13, 0.22),
					"botas": Color(0.92, 0.95, 1.0),
					"manos": Color(0.98, 0.86, 0.77),
					"ojos": Color(0.3, 0.85, 1.0),
					"cinta": Color(0.37, 0.85, 1.0),
					"ki": Color(0.35, 0.8, 1.0),
					"ki_nucleo": Color(0.92, 1.0, 1.0),
				},
				"super": {"nombre": "Zettai Reido", "dano": 720.0},
				"frases": {
					"entrada": "Terminemos con esto rápido.",
					"tecnica": "Zettai... Reido.",
					"victoria": "Demasiado lento.",
					"derrota": "Imposible... me has... alcanzado...",
				},
			}
	push_error("No existe el personaje '%s'" % id)
	return {}
