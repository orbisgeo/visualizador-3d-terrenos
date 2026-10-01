# Visualizador topográfico

Aplicação estática otimizada para celular com:

- mapa do mosaico georreferenciado e camadas liga/desliga;
- curvas de nível pretas e rotuladas pelo campo `ELEV`; aproxime para tocá-las
  e consultar a cota sem confundir linhas vizinhas;
- corpos hídricos em azul;
- poligonal e quadro de áreas/perímetros em SIRGAS 2000 / UTM 25S;
- ferramenta para traçar e consultar perfis de elevação do DSM, com eixo
  horizontal expandido e navegável por toque, mouse ou teclado;

Visualização publicada: <https://visualizador-3d-terrenos.vercel.app/>.

## Preparar estes dados

Instale `numpy` e `rasterio` no Python normal. Coloque os arquivos-fonte na
pasta pai do repositório:

```text
dsm_cm.tif
mosaico.tif
cv.geojson
poligonal.geojson
corpos_hidricos.geojson
```

Execute na pasta do repositório:

```powershell
python prepare_site_data.py
```

O preparo recorta o DSM para a cobertura do mosaico, reduz o mosaico para no
máximo 4096 pixels no maior lado e o codifica em WebP para economizar dados no
celular. As curvas mantêm o campo `ELEV` e são simplificadas com tolerância de
12 cm. As medidas de área e perímetro são calculadas em metros no CRS projetado
EPSG:31985. Também são preparados uma grade compacta para os perfis e a
camada hidrográfica. O DSM intermediário `data/dsm_cm.npy` fica fora do Git.

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
