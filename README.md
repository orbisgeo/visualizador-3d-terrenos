# Visualizador 3D

Página estática para exibir modelos `.glb` interativos em desktop e celular.
O modelo Mari1 é o exemplo padrão; nenhum framework ou etapa de build é
necessário.

Visualização publicada: <https://visualizador-3d-terrenos.vercel.app/>.

## Ver localmente

Abra um terminal nesta pasta e execute:

```powershell
python -m http.server 8000
```

Abra <http://localhost:8000>. O `.glb` deve ficar na mesma pasta do `index.html`
ou em uma pasta interna referenciada pela URL.

## Reutilizar com outro modelo

Use o modelo padrão em `./terreno_mari1.glb`, ou passe outro endereço `.glb`
pela query string:

```text
https://SEU-SITE.vercel.app/?model=./modelos/outro.glb&title=Outro%20terreno
```

`model` aceita um caminho relativo a esta página ou uma URL HTTP/HTTPS pública.
Para carregar um arquivo hospedado em outro domínio, esse servidor precisa
permitir requisições CORS do domínio desta página. `title` é opcional.

Para incluir modelos próprios no repositório, coloque-os em `modelos/` e
referencie o caminho na URL. O GitHub não aceita arquivos acima de 100 MB e o
Vercel Hobby limita cada arquivo estático a 100 MB; para modelos maiores, use
armazenamento/CDN de arquivos e passe a URL pública por `model`.

## Publicar

O projeto é estático: importe este repositório no Vercel com o diretório raiz
`web` (ou importe o próprio repositório, caso `web` seja a raiz dele), sem
comando de build e sem diretório de saída especial. Cada push na branch
principal publica uma nova versão.

## Arquivos

- `index.html`: visualizador reutilizável.
- `terreno_mari1.glb`: modelo de demonstração com mosaico incorporado.
- `vercel.json`: configuração de URLs e cache para os modelos.
