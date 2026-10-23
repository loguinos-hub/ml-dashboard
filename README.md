# Painel de Vendas - Mercado Livre

Painel local para acompanhar vendas, custos, investimento em anúncios e lucro,
além de editar e criar anúncios no Mercado Livre.

## O que ele faz

- Importa seus pedidos do Mercado Livre (produto, SKU, quantidade, valor, taxa do ML, tipo de envio: Full/Flex/Coleta/Agência)
- Permite cadastrar o custo de cada produto por SKU
- Permite lançar quanto você investiu em anúncios patrocinados por dia
- Mostra um relatório diário: vendas, taxas, custo, investimento em ads e lucro líquido
- Lista seus anúncios, permite editar preço/estoque/SKU e criar anúncios novos

## 1. Criar o app no Mercado Livre

O Mercado Livre não aceita mais `localhost` como Redirect URI — precisa de um endereço
público real em HTTPS. A forma mais simples e gratuita de conseguir isso é o **ngrok**,
que cria um túnel do tipo `https://alguma-coisa.ngrok-free.app` apontando pro seu
computador.

### 1.1 Instalar e configurar o ngrok

1. Crie uma conta grátis em https://ngrok.com
2. Instale o ngrok (https://ngrok.com/download) e autentique:
   ```bash
   ngrok config add-authtoken SEU_TOKEN_AQUI
   ```
   (o token fica no painel do ngrok, em "Your Authtoken")
3. No painel do ngrok, vá em **Domains** → crie um **domínio estático grátis**
   (ex: `painel-ml-fulano.ngrok-free.app`). Isso garante que a URL não muda toda vez
   que você reiniciar o túnel.
4. Deixe esse domínio guardado, vamos usar nos próximos passos.

### 1.2 Criar o app no Mercado Livre

1. Acesse https://developers.mercadolivre.com.br e faça login com sua conta de vendedor
2. Vá em "Minhas aplicações" → "Criar nova aplicação"
3. Em **Redirect URI**, use o domínio do ngrok que você reservou:
   `https://SEU-SUBDOMINIO.ngrok-free.app/auth/callback`
4. Marque **Refresh Token** nos fluxos OAuth (essencial para o token renovar sozinho)
5. Em Negócios, marque **Mercado Livre**
6. Em Permissões, marque "Leitura e escrita" em: Usuários, Publicação e sincronização, Venda e envios de um produto
7. Em Tópicos (webhooks), pode deixar tudo desmarcado
8. Se pedir uma "URL de retorno de notificação", coloque a mesma URL do ngrok, não será usada de fato
9. Copie o **Client ID** e o **Client Secret**

## 2. Configurar o projeto

```bash
cd ml-dashboard
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edite o arquivo `.env` e preencha:

```
ML_CLIENT_ID=seu_client_id
ML_CLIENT_SECRET=seu_client_secret
```

## 3. Rodar

Em um terminal, suba o painel (HTTP normal, o ngrok cuida do HTTPS):

```bash
uvicorn app.main:app --reload --port 8000
```

Em **outro terminal**, abra o túnel com o domínio que você reservou:

```bash
ngrok http 8000 --domain=SEU-SUBDOMINIO.ngrok-free.app
```

Deixe esse segundo terminal aberto enquanto estiver usando o painel — é ele que
mantém a URL pública ativa.

Agora abra **https://SEU-SUBDOMINIO.ngrok-free.app** no navegador (não mais `localhost`).
Clique em **Conectar com Mercado Livre**, autorize o app, e você será redirecionado de
volta ao painel.

## 4. Primeiros passos no painel

1. Vá em **Custos por SKU** e cadastre o custo de cada produto (isso define o lucro calculado)
2. Vá em **Relatório** e clique em **Sincronizar pedidos do Mercado Livre**
3. (Opcional) Vá em **Investimento em Ads** e lance quanto gastou em publicidade por dia
4. O relatório diário mostra vendas, taxas do ML, custo de produto, ads e lucro

## Observações importantes

- O token de acesso do Mercado Livre expira a cada 6h; com o escopo `offline_access`
  o sistema renova automaticamente usando o refresh token, sem precisar logar de novo.
- A sincronização busca os pedidos dos últimos N dias (ajustável pelo filtro de período)
  e salva localmente no arquivo `ml_dashboard.db` (SQLite) — roda tudo na sua máquina,
  nada vai para servidores externos.
- Criar anúncio exige o **ID da categoria** do Mercado Livre (ex: `MLB1055`). Se não souber
  qual categoria usar, você pode consultar a API de categorias do próprio ML ou criar um
  anúncio de teste pelo site para descobrir a categoria certa.
- O investimento em Ads (Product Ads) não é lançado automaticamente — a API de publicidade
  do Mercado Livre exige permissões extras de "Advertiser" que não vêm habilitadas por padrão.
  Por isso esse valor é lançado manualmente na tela "Investimento em Ads". Se depois você
  conseguir acesso à API de Advertising, dá para automatizar esse ponto também.
