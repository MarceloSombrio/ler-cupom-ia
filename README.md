# 🤖 Leitor de Cupom Fiscal

Uma aplicação web inteligente que usa IA (GPT-4o-mini) para analisar cupons fiscais de delivery e extrair informações automaticamente.

## ✨ Funcionalidades

- 📸 **Upload de imagens** (PNG, JPG, PDF)
- 📱 **Captura via câmera** do celular
- 🤖 **Análise com IA** usando GPT-4o-mini
- ⚡ **Processamento rápido** com contador de tempo
- 🎯 **Identificação automática** de marcas (iFood, Zé Delivery, etc.)
- 📊 **Extração completa** de dados do cupom

## 🚀 Deploy no Vercel

### Pré-requisitos
- Conta no [Vercel](https://vercel.com)
- Conta no [GitHub](https://github.com)
- Chave da API OpenAI

### Passos para Deploy

1. **Envie para GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/leitor-cupom-fiscal.git
   git push -u origin main
   ```

2. **Conecte no Vercel:**
   - Acesse [vercel.com](https://vercel.com)
   - Clique em "New Project"
   - Conecte sua conta do GitHub
   - Selecione o repositório
   - Configure a variável de ambiente `OPENAI_API_KEY`

3. **Configure Variáveis de Ambiente:**
   - No Vercel, vá em Settings → Environment Variables
   - Adicione: `OPENAI_API_KEY` com sua chave da OpenAI

## 🛠️ Desenvolvimento Local

### Instalação
```bash
pip install -r requirements.txt
```

### Execução
```bash
python app.py
```

Acesse: http://localhost:5000

## 📋 Tecnologias

- **Backend**: Python + Flask
- **IA**: OpenAI GPT-4o-mini
- **OCR**: Tesseract (fallback)
- **Frontend**: HTML + CSS + JavaScript
- **Deploy**: Vercel

## 📱 Como Usar

1. **Upload de arquivo** ou **captura via câmera**
2. **Clique em "Extrair Dados"**
3. **Aguarde a análise** (com contador de tempo)
4. **Visualize os dados** extraídos em formato legível

## 🎯 Dados Extraídos

- 🏪 Nome do estabelecimento
- 📋 Número do pedido
- 👤 Dados do cliente
- 📅 Datas e horários
- 💰 Valores e taxas
- 🚚 Tipo de entrega
- 💳 Forma de pagamento
- 🔍 Marca/aplicativo identificado

## 📄 Licença

MIT License - veja o arquivo LICENSE para detalhes.

## 🤝 Contribuições

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues e pull requests.

