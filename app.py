import os
import io
import re
import base64
from typing import Dict, Any, List, Optional, Tuple

from flask import Flask, render_template, request, jsonify
from PIL import Image
import numpy as np
from openai import OpenAI

try:
    import cv2  # type: ignore
except Exception:
    cv2 = None

from pdf2image import convert_from_bytes

# Tentar carregar variáveis de ambiente de arquivo .env
try:
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value
    print("✅ Arquivo .env carregado")
except FileNotFoundError:
    print("ℹ️ Arquivo .env não encontrado - usando variáveis de ambiente do sistema")
except Exception as e:
    print(f"⚠️ Erro ao carregar .env: {e}")

# Aplicação otimizada para usar apenas IA (sem Tesseract)
print("🚀 Aplicação iniciada - Modo IA apenas")

# Configure OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Verificar API Key
if not OPENAI_API_KEY or len(OPENAI_API_KEY) < 20:
    print("❌ AVISO: OpenAI API Key não configurada ou inválida!")
    print("Configure a variável de ambiente OPENAI_API_KEY")
else:
    print(f"✅ OpenAI API Key configurada: {OPENAI_API_KEY[:10]}...")

client = OpenAI(api_key=OPENAI_API_KEY)

app = Flask(__name__)


# ------------------------
# Helpers: Files and Images
# ------------------------

def _read_file_storage_to_bytes() -> Tuple[Optional[bytes], Optional[str]]:
    file = request.files.get('file')
    if file and file.filename:
        return file.read(), file.filename.lower()
    # If not via file input, check base64 from camera
    b64_data = request.form.get('image_base64')
    if b64_data:
        try:
            header, encoded = b64_data.split(',') if ',' in b64_data else ('', b64_data)
            return base64.b64decode(encoded), 'camera_capture.png'
        except Exception:
            return None, None
    return None, None


def _load_image_from_bytes(file_bytes: bytes) -> List[Image.Image]:
    """Return list of PIL Images. If PDF, convert pages; else single image."""
    if _looks_like_pdf(file_bytes):
        pages = convert_from_bytes(file_bytes, fmt='png')
        return pages
    else:
        image = Image.open(io.BytesIO(file_bytes))
        return [image.convert('RGB')]


def _looks_like_pdf(file_bytes: bytes) -> bool:
    return file_bytes[:4] == b'%PDF'


# ------------------------
# OCR Preprocessing
# ------------------------

def _preprocess_image_for_ocr(pil_image: Image.Image) -> Image.Image:
    if cv2 is None:
        # Fallback: simple resize to improve OCR at lower resolutions
        w, h = pil_image.size
        scale = 1 if max(w, h) >= 1200 else 1200 / max(w, h)
        if scale > 1:
            pil_image = pil_image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        return pil_image

    # Convert PIL to OpenCV
    np_img = np.array(pil_image)
    if np_img.ndim == 3 and np_img.shape[2] == 3:
        img = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)
    else:
        img = np_img

    # Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    # Adaptive threshold
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 31, 10)
    # Mild denoise
    denoised = cv2.fastNlMeansDenoising(th, None, 15, 7, 21)
    # Upscale to help OCR
    h, w = denoised.shape[:2]
    scale = 1 if max(w, h) >= 1500 else 1500 / max(w, h)
    resized = cv2.resize(denoised, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    return Image.fromarray(resized)


def _preprocess_image_for_ai(pil_image: Image.Image) -> Image.Image:
    """Preprocessa imagem especificamente para análise de IA - otimizada para velocidade"""
    # Converter para RGB se necessário
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    # Redimensionar para tamanho otimizado (mais rápido)
    w, h = pil_image.size
    target_size = 1200  # Tamanho ideal para velocidade vs qualidade
    
    if max(w, h) != target_size:
        # Calcular nova dimensão mantendo proporção
        if w > h:
            new_w = target_size
            new_h = int((h * target_size) / w)
        else:
            new_h = target_size
            new_w = int((w * target_size) / h)
        
        pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS)
    
    return pil_image


# ------------------------
# OCR and Extraction
# ------------------------

# Função OCR removida - usando apenas IA


def _detect_brand(full_text: str) -> str:
    text = full_text.upper()
    clean_text = re.sub(r'[^\w\s]', ' ', text)
    clean_text = re.sub(r'\s+', ' ', clean_text)
    ze_patterns = ["ZÉ DELIVERY", "ZE DELIVERY", "ZE\u0301 DELIVERY", "ZÉ-DELIVERY", "ZÉDELIVERY", "ZEDELIVERY"]
    if any(k in clean_text for k in ze_patterns):
        return "ZE DELIVERY"
    ifood_patterns = ["IFOOD", "I-FOOD", "I FOOD"]
    if any(k in clean_text for k in ifood_patterns):
        return "IFOOD"
    if "FOOD" in clean_text and ("I" in clean_text or "1" in clean_text):
        return "IFOOD"
    return "Aplicativo Proprio"


def _extract_datetime(full_text: str) -> Optional[str]:
    text = full_text
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        if "CRIADO EM:" in ln.upper():
            date_patterns = [
                r"(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
                r"(\d{4}[\-/]\d{1,2}[\-/]\d{1,2})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
            ]
            for pat in date_patterns:
                m = re.search(pat, ln)
                if m:
                    return f"{m.group(1)} {m.group(2)}"
    patterns = [
        r"(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
        r"(\d{4}[\-/]\d{1,2}[\-/]\d{1,2})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return f"{m.group(1)} {m.group(2)}"
    return None


def _extract_delivery_fee(full_text: str) -> Optional[str]:
    text = full_text.upper()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    money_patterns = [
        r"R\$\s*\d+[.,]?\d{0,3}[.,]\d{2}",
        r"\d+[.,]?\d{0,3}[.,]\d{2}",
    ]
    priority_keywords = ["TAXA DE ENTREGA", "TAXA ENTREGA", "FRETE", "ENTREGA"]
    secondary_keywords = ["SERVIÇO", "SERVICO", "TAXA DE SERVIÇO", "TAXA DE SERVICO"]
    for ln in lines:
        if any(kw in ln for kw in priority_keywords):
            for pat in money_patterns:
                m = re.search(pat, ln)
                if m:
                    val = m.group(0)
                    if not val.startswith("R$"):
                        val = "R$ " + val
                    return val.replace(" ", "")
    for ln in lines:
        if any(kw in ln for kw in secondary_keywords):
            for pat in money_patterns:
                m = re.search(pat, ln)
                if m:
                    val = m.group(0)
                    if not val.startswith("R$"):
                        val = "R$ " + val
                    return val.replace(" ", "")
    return None


# ------------------------
# AI Functions
# ------------------------

def _ai_analyze_image(image_bytes: bytes) -> Dict[str, Any]:
    import json  # Import no início da função
    
    try:
        print(f"🔍 Iniciando análise IA - Tamanho da imagem: {len(image_bytes)} bytes")
        
        # Verificar se a API key está configurada
        if not OPENAI_API_KEY or len(OPENAI_API_KEY) < 20:
            print("❌ API Key não configurada corretamente")
            return None
        
        # Verificar tamanho da imagem (limite do OpenAI: 20MB)
        if len(image_bytes) > 20 * 1024 * 1024:
            print(f"❌ Imagem muito grande: {len(image_bytes)} bytes (limite: 20MB)")
            return None
            
        base64_string = base64.b64encode(image_bytes).decode('utf-8')
        print(f"📤 Enviando imagem para OpenAI (base64: {len(base64_string)} chars)")
        
        # Verificar se a string base64 não é muito grande
        if len(base64_string) > 1000000:  # ~750KB de imagem
            print(f"⚠️ Imagem grande, pode causar timeout")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um especialista em análise de cupons fiscais de delivery. Analise a imagem e extraia todas as informações visíveis em formato JSON estruturado."},
                {"role": "user", "content": [
                    {"type": "text", "text": """Analise esta imagem de cupom fiscal e extraia TODAS as informações visíveis em formato JSON:

{
  "marca": "IFOOD", "ZE_DELIVERY", "UBER_EATS", "RAPPI" ou "APLICATIVO_PROPRIO",
  "nome_estabelecimento": "nome do restaurante/estabelecimento",
  "numero_pedido": "número do pedido",
  "nome_cliente": "nome do cliente",
  "telefone_cliente": "telefone do cliente",
  "endereco_entrega": "endereço de entrega completo",
  "data_criacao": "data e hora de criação do pedido",
  "data_entrega": "data e hora de entrega",
  "tipo_entrega": "Retirada em Loja" ou "Entrega",
  "forma_pagamento": "PIX", "Cartão", "Dinheiro" ou outro,
  "subtotal": "valor dos produtos",
  "taxa_entrega": "taxa de entrega",
  "taxa_servico": "taxa de serviço",
  "total_geral": "valor total final",
  "historico_cliente": "informações sobre pedidos anteriores",
  "observacoes": "observações especiais"
}

REGRAS IMPORTANTES:
- MARCA: Identifique pelo logo/texto (iFood→IFOOD, Zé Delivery→ZE_DELIVERY, Uber Eats→UBER_EATS, Rappi→RAPPI, outros→APLICATIVO_PROPRIO)
- VALORES: Use formato "R$ X,XX" 
- DATAS: Mantenha formato original da imagem
- Se alguma informação não estiver visível, use "null"
- Retorne APENAS o JSON válido, sem explicações"""},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_string}"}}
                ]}
            ],
            max_tokens=2000,
            temperature=0.1,
            timeout=60  # Timeout de 60 segundos
        )
        
        ai_result = response.choices[0].message.content.strip()
        print(f"📥 Resposta recebida da IA: {len(ai_result)} caracteres")
        
        # Limpar possíveis caracteres extras antes do JSON
        if ai_result.startswith('```json'):
            ai_result = ai_result[7:]
        if ai_result.endswith('```'):
            ai_result = ai_result[:-3]
        if ai_result.startswith('```'):
            ai_result = ai_result[3:]
        ai_result = ai_result.strip()
        
        print(f"🧹 JSON limpo: {ai_result[:100]}...")
        
        parsed_result = json.loads(ai_result)
        print("✅ JSON parseado com sucesso!")
        return parsed_result
        
    except json.JSONDecodeError as e:
        print(f"❌ Erro ao fazer parse do JSON: {e}")
        print(f"📄 Conteúdo recebido: {ai_result[:200]}...")
        return None
    except Exception as e:
        print(f"❌ Erro na análise AI da imagem: {e}")
        print(f"🔍 Tipo do erro: {type(e).__name__}")
        print(f"🔍 Detalhes do erro: {str(e)}")
        return None


def _format_cupom_data(data: Dict[str, Any]) -> str:
    """Formata os dados do cupom no formato legível solicitado"""
    try:
        marca_map = {
            "IFOOD": "iFood",
            "ZE_DELIVERY": "Zé Delivery", 
            "UBER_EATS": "Uber Eats",
            "RAPPI": "Rappi",
            "APLICATIVO_PROPRIO": "Aplicativo Próprio"
        }
        
        marca = marca_map.get(data.get("marca", "APLICATIVO_PROPRIO"), "Aplicativo Próprio")
        nome_estabelecimento = data.get("nome_estabelecimento", "—")
        numero_pedido = data.get("numero_pedido", "—")
        nome_cliente = data.get("nome_cliente", "—")
        telefone_cliente = data.get("telefone_cliente", "—")
        endereco_entrega = data.get("endereco_entrega") or "—"
        data_criacao = data.get("data_criacao", "—")
        data_entrega = data.get("data_entrega", "—")
        tipo_entrega = data.get("tipo_entrega", "—")
        forma_pagamento = data.get("forma_pagamento", "—")
        subtotal = data.get("subtotal", "—")
        taxa_entrega = data.get("taxa_entrega", "—")
        taxa_servico = data.get("taxa_servico", "—")
        total_geral = data.get("total_geral", "—")
        historico_cliente = data.get("historico_cliente") or "—"
        observacoes = data.get("observacoes") or "—"
        
        formatted_text = f"""🏪 {nome_estabelecimento}

📋 Pedido nº: {numero_pedido}
👤 Cliente: {nome_cliente}

📅 Criado em: {data_criacao}

💳 Método de pagamento:
Pagamento na entrega – {forma_pagamento}

🚚 Tipo de entrega:
{tipo_entrega}

📅 Data de entrega:
{data_entrega}

📞 Telefone: {telefone_cliente}
🏠 Endereço: {endereco_entrega}
📊 Histórico do cliente: {historico_cliente}

💰 Resumo da compra

Total Produtos: {subtotal}

Taxas:
Taxa de Entrega: {taxa_entrega}
Taxa de Serviço: {taxa_servico}

Total Geral: {total_geral}

🔍 Informações do Sistema
Marca/Aplicativo: {marca}
Observações: {observacoes}"""
        
        return formatted_text
    except Exception as e:
        print(f"Erro ao formatar dados: {e}")
        return "❌ Erro ao formatar os dados do cupom"


def _ai_enhance_extraction(text: str) -> Dict[str, Any]:
    try:
        prompt = f"""
Analise este texto extraído de um cupom fiscal por OCR e extraia as seguintes informações:

TEXTO OCR:
{text}

Extraia APENAS estas informações em formato JSON:
{{
  "marca": "ZE DELIVERY", "IFOOD" ou "Aplicativo Proprio",
  "data_hora": "data e hora do pedido (formato: DD/MM/AAAA HH:MM)",
  "frete_ou_taxa": "valor da taxa de entrega em R$ (ex: R$5,50)"
}}

REGRAS:
- Se encontrar "ZÉ DELIVERY" ou "ZE DELIVERY" → marca = "ZE DELIVERY"
- Se encontrar "IFOOD" ou "I-FOOD" → marca = "IFOOD"
- Caso contrário → marca = "Aplicativo Proprio"
- Para data/hora, procure por "Criado Em:" primeiro, depois qualquer data/hora
- Para frete, procure por "taxa de entrega", "frete", "entrega" (não taxa de serviço)
- Se não encontrar alguma informação, use null
- Responda APENAS com o JSON, sem explicações
"""
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1
        )
        ai_result = response.choices[0].message.content.strip()
        import json
        return json.loads(ai_result)
    except Exception as e:
        print(f"Erro na análise AI: {e}")
        return None


# ------------------------
# Extractor (IA principal)
# ------------------------

def extract_all(text: str, image_bytes: bytes = None) -> Dict[str, Any]:
    use_ai = request.args.get('noai') != 'true'

    # Usar APENAS análise de imagem com IA se disponível
    if use_ai and image_bytes:
        print("🤖 Analisando imagem diretamente com IA...")
        ai_image_result = _ai_analyze_image(image_bytes)
        if ai_image_result:
            print("✅ Análise de imagem com IA bem-sucedida!")
            try:
                # Retornar apenas o texto formatado
                formatted_text = _format_cupom_data(ai_image_result)
                return {
                    "texto_formatado": formatted_text,
                    "metodo": "IA_IMAGEM"
                }
            except Exception as e:
                print(f"❌ Erro ao formatar dados: {e}")
                return {
                    "texto_formatado": f"❌ Erro: Falha ao formatar dados extraídos: {str(e)}", 
                    "metodo": "ERRO_FORMATACAO"
                }
        else:
            print("❌ Falha na análise de imagem com IA")
            return {
                "texto_formatado": "❌ Erro: Falha na análise da imagem com IA\n\nPossíveis causas:\n• API Key inválida\n• Imagem muito grande\n• Problema de conexão\n• Formato de imagem não suportado", 
                "metodo": "ERRO_IA"
            }

    # Se não há imagem ou IA desabilitada, usar OCR como fallback
    ocr_result = {
        "marca": _detect_brand(text),
        "data_hora": _extract_datetime(text),
        "frete_ou_taxa": _extract_delivery_fee(text),
    }
    
    return {
        "texto_formatado": f"⚠️ Modo OCR (sem IA):\nMarca: {ocr_result['marca']}\nData/Hora: {ocr_result['data_hora']}\nTaxa: {ocr_result['frete_ou_taxa']}", 
        "metodo": "OCR_FALLBACK"
    }


# ------------------------
# Routes
# ------------------------

@app.get('/')
def index():
    return render_template('index.html')


@app.get('/test-api')
def test_api():
    """Endpoint para testar a API key"""
    try:
        # Teste simples com texto
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Responda apenas: OK"}],
            max_tokens=10,
            temperature=0.0
        )
        result = response.choices[0].message.content.strip()
        return {
            "status": "success",
            "api_key_valid": True,
            "response": result,
            "api_key_preview": OPENAI_API_KEY[:10] + "..." if OPENAI_API_KEY else "NOT_SET"
        }
    except Exception as e:
        return {
            "status": "error",
            "api_key_valid": False,
            "error": str(e),
            "api_key_preview": OPENAI_API_KEY[:10] + "..." if OPENAI_API_KEY else "NOT_SET"
        }


@app.post('/extract')
def extract_route():
    file_bytes, filename = _read_file_storage_to_bytes()
    if not file_bytes:
        return "❌ Erro: Nenhum arquivo ou imagem recebida.", 400
    try:
        images = _load_image_from_bytes(file_bytes)
        
        # Processar primeira imagem para IA (otimizada para análise visual)
        first_image_bytes = None
        if images:
            # Usar processamento otimizado para IA
            processed_img = _preprocess_image_for_ai(images[0])
            img_buffer = io.BytesIO()
            processed_img.save(img_buffer, format='PNG', quality=95)
            first_image_bytes = img_buffer.getvalue()
        
        # Não precisamos mais de OCR - usando apenas IA
        full_text = ""

        data = extract_all(full_text, first_image_bytes)
        return data.get("texto_formatado", "❌ Erro: Não foi possível processar a imagem.")
    except Exception as e:
        return f"❌ Erro: Falha ao processar arquivo: {str(e)}", 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    app.run(host='0.0.0.0', port=port, debug=True)
