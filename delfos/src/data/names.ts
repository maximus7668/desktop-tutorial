// Nombres en español para selecciones y algunos clubes muy conocidos.
const ES: Record<string, string> = {
  Spain: 'España', Germany: 'Alemania', France: 'Francia', Italy: 'Italia', England: 'Inglaterra',
  Netherlands: 'Países Bajos', Belgium: 'Bélgica', Croatia: 'Croacia', Switzerland: 'Suiza', Denmark: 'Dinamarca',
  Scotland: 'Escocia', Wales: 'Gales', Sweden: 'Suecia', Norway: 'Noruega', Poland: 'Polonia', Czechia: 'Chequia',
  'Czech Republic': 'Chequia', Turkey: 'Turquía', 'Türkiye': 'Turquía', Greece: 'Grecia', Hungary: 'Hungría',
  Ukraine: 'Ucrania', Romania: 'Rumanía', 'Republic of Ireland': 'Irlanda', Ireland: 'Irlanda',
  'Northern Ireland': 'Irlanda del Norte', Slovakia: 'Eslovaquia', Slovenia: 'Eslovenia', Finland: 'Finlandia',
  Iceland: 'Islandia', 'Bosnia and Herzegovina': 'Bosnia y Herzegovina', 'Bosnia-Herzegovina': 'Bosnia y Herzegovina',
  'North Macedonia': 'Macedonia del Norte', Belarus: 'Bielorrusia', Cyprus: 'Chipre', Luxembourg: 'Luxemburgo',
  Azerbaijan: 'Azerbaiyán', Kazakhstan: 'Kazajistán', Latvia: 'Letonia', Lithuania: 'Lituania', 'Faroe Islands': 'Islas Feroe',
  Brazil: 'Brasil', Mexico: 'México', 'United States': 'Estados Unidos', USA: 'Estados Unidos', Canada: 'Canadá',
  Japan: 'Japón', 'South Korea': 'Corea del Sur', Morocco: 'Marruecos', Egypt: 'Egipto', Peru: 'Perú',
  'Bayern Munich': 'Bayern Múnich', 'Internazionale': 'Inter', 'Inter Milan': 'Inter',
};

export const esName = (n: string) => ES[n] ?? n;
