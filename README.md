# Visualizador topográfico

Aplicação estática otimizada para celular com:

- mapa do mosaico georreferenciado e camadas liga/desliga;
- curvas de nível pretas e rotuladas pelo campo `ELEV`; aproxime para tocá-las
  e consultar a cota sem confundir linhas vizinhas;
- corpos hídricos em azul;
- poligonal e quadro de áreas/perímetros em SIRGAS 2000 / UTM 25S;
- perfil do terreno baseado no DTM filtrado, com interpolações a cada 0,5 m e
  trechos visíveis/ocultos para observador a 1,7 m;

Visualização publicada: <https://visualizador-3d-terrenos.vercel.app/>.

## Preparar estes dados

Instale `numpy` e `rasterio` no Python normal. Coloque os arquivos-fonte na
pasta pai do repositório:

```text
dtm_cm.tif
mosaico.tif
cv.geojson
poligonal.geojson
corpos_hidricos.geojson
```

Execute na pasta do repositório:

```powershell
python prepare_site_data.py
```

O perfil usa `dtm_cm.tif`, o modelo digital do terreno filtrado, e o interpola
bilinearmente ao longo da linha; o início do traçado representa o observador,
com altura dos olhos de 1,7 m. Os pontos visíveis e ocultos são separados pelo
horizonte acumulado do relevo. O gráfico informa seu exagero vertical, portanto
a forma desenhada não deve ser interpretada como uma perspectiva de câmera. O
preparo reduz o mosaico para no máximo 4096 pixels no maior lado e o codifica
em WebP para economizar dados no celular. As curvas mantêm o campo `ELEV` e
são simplificadas com tolerância de 12 cm. As medidas de área e perímetro são
calculadas em metros no CRS projetado EPSG:31985. Também são preparados uma
grade compacta para perfis e a camada hidrográfica.

## Executar localmente

Na pasta do repositório, execute:

```powershell
python -m http.server 8000
```

Abra <http://localhost:8000>. Sirva a pasta por HTTP; abrir o `index.html`
diretamente como arquivo pode impedir o carregamento dos dados.

## Publicação

O repositório é o diretório raiz do projeto estático no Vercel. Cada push para
`main` publica uma atualização automaticamente. Não há etapa de build.
