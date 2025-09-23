#!/usr/bin/env python3
# -*- coding: utf-8 -*-

print("🔍 Iniciando teste...")

try:
    from dotenv import load_dotenv
    import os
    import io
    import re
    import base64
    import json
    import logging
    from typing import Dict, Any, List, Optional, Tuple
    from datetime import datetime
    
    from flask import Flask, render_template, request, jsonify
    from PIL import Image
    import numpy as np
    from openai import OpenAI
    from openai import RateLimitError, AuthenticationError, APIConnectionError, APIError
    from pdf2image import convert_from_bytes
    
    print("✅ Imports OK")
    
    load_dotenv()
    print("✅ .env carregado")
    
    # Carregar chave APENAS de arquivos externos (SEGURANÇA)
    api_key = None
    
    # 1. Tentar carregar do arquivo .env
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print("✅ Chave carregada do arquivo .env")
    
    # 2. Se não encontrou no .env, tentar carregar de arquivo separado
    if not api_key:
        try:
            with open('api_key.txt', 'r', encoding='utf-8') as f:
                api_key = f.read().strip()
            print("✅ Chave carregada do arquivo api_key.txt")
        except FileNotFoundError:
            print("❌ Arquivo api_key.txt não encontrado")
    
    # 3. Se ainda não encontrou, tentar variável de ambiente do sistema
    if not api_key:
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key:
            print("✅ Chave carregada da variável de ambiente do sistema")
    print(f"✅ Chave encontrada: {bool(api_key)}")
    
    if not api_key:
        print("❌ ERRO: Chave não encontrada!")
        exit(1)
    
    client = OpenAI(api_key=api_key)
    print("✅ Cliente OpenAI criado")
    
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('app.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    
    app = Flask(__name__)
    
    # ------------------------
    # Funções de Processamento
    # ------------------------
    
    def _read_file_storage_to_bytes() -> Tuple[Optional[bytes], Optional[str]]:
        """Lê arquivo enviado via upload ou base64"""
        file = request.files.get('file')
        if file and file.filename:
            return file.read(), file.filename.lower()
        
        # Se não via file input, check base64 from camera
        b64_data = request.form.get('image_base64')
        if b64_data:
            try:
                header, encoded = b64_data.split(',') if ',' in b64_data else ('', b64_data)
                return base64.b64decode(encoded), 'camera_capture.png'
            except Exception:
                return None, None
        return None, None
    
    def _load_image_from_bytes(file_bytes: bytes) -> List[Image.Image]:
        """Retorna lista de imagens PIL. Se PDF, converte páginas; senão imagem única."""
        if file_bytes[:4] == b'%PDF':
            pages = convert_from_bytes(file_bytes, fmt='png')
            return pages
        else:
            image = Image.open(io.BytesIO(file_bytes))
            return [image.convert('RGB')]
    
    def _preprocess_image_for_ai(pil_image: Image.Image) -> Image.Image:
        """Preprocessa imagem para análise de IA - otimizada para velocidade"""
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        
        w, h = pil_image.size
        target_size = 1200
        
        if max(w, h) != target_size:
            if w > h:
                new_w = target_size
                new_h = int((h * target_size) / w)
            else:
                new_h = target_size
                new_w = int((w * target_size) / h)
            pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS)
        
        return pil_image
    
    def _ai_analyze_image(image_bytes: bytes) -> Dict[str, Any]:
        """Analisa imagem com IA e extrai dados do cupom"""
        logger.info("🔄 Iniciando análise de imagem com IA...")
        
        try:
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            logger.info("📤 Enviando requisição para OpenAI...")
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Analise cupons fiscais de delivery. Se não conseguir identificar dados de cupom, retorne erro."},
                    {"role": "user", "content": [
                        {"type": "text", "text": """Analise esta imagem e extraia dados do cupom fiscal de delivery em JSON.

IMPORTANTE: Se a imagem NÃO contém um cupom fiscal de delivery legível, retorne:
{"erro": "Foto não está conforme solicitada, tente novamente"}

Se contém cupom legível, extraia em JSON:

{
  "marca": "IFOOD", "ZE_DELIVERY" ou "APLICATIVO_PROPRIO",
  "nome_estabelecimento": "nome do restaurante",
  "numero_pedido": "número do pedido",
  "nome_cliente": "nome do cliente",
  "telefone_cliente": "telefone",
  "endereco_entrega": "endereço",
  "data_criacao": "data/hora criação",
  "data_entrega": "data/hora entrega",
  "tipo_entrega": "Retirada em Loja" ou "Entrega",
  "forma_pagamento": "PIX", "Cartão" ou outro,
  "subtotal": "valor produtos",
  "taxa_entrega": "taxa entrega",
  "taxa_servico": "taxa serviço",
  "total_geral": "total final",
  "historico_cliente": "pedidos anteriores",
  "observacoes": "observações"
}

MARCA: iFood/IFOOD→IFOOD, Zé Delivery→ZE_DELIVERY, Uber Eats→UBER_EATS, Rappi→RAPPI, outros→APLICATIVO_PROPRIO
Valores: R$ X,XX. Datas: formato original. Se não visível: null. Apenas JSON."""},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_string}"}}
                    ]}
                ],
                max_tokens=1500,
                temperature=0.0
            )
            
            logger.info("✅ Resposta recebida da OpenAI!")
            ai_result = response.choices[0].message.content.strip()
            
            # Limpar possíveis caracteres extras antes do JSON
            if ai_result.startswith('```json'):
                ai_result = ai_result[7:]
            if ai_result.endswith('```'):
                ai_result = ai_result[:-3]
            ai_result = ai_result.strip()
            
            result = json.loads(ai_result)
            
            if isinstance(result, dict) and "erro" in result:
                logger.warning(f"⚠️ IA detectou problema na imagem: {result['erro']}")
                return {"erro": result["erro"]}
            
            logger.info("✅ Análise de imagem concluída com sucesso!")
            return result
            
        except (RateLimitError, AuthenticationError, APIConnectionError, APIError) as e:
            logger.error(f"❌ Erro da API OpenAI: {e}")
            return {"erro": f"Erro da API: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error(f"❌ ERRO: Resposta da IA não é JSON válido: {e}")
            return {"erro": "Erro interno: resposta inválida da IA"}
        except Exception as e:
            logger.error(f"❌ ERRO INESPERADO na análise de imagem: {e}")
            return {"erro": f"Erro inesperado: {str(e)}"}
    
    def _format_cupom_data(data: Dict[str, Any]) -> str:
        """Formata os dados do cupom no formato legível"""
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
            logger.error(f"Erro ao formatar dados: {e}")
            return "❌ Erro ao formatar os dados do cupom"
    
    @app.route('/')
    def home():
        logger.info("🏠 Página inicial acessada")
        return render_template('index.html')
    
    @app.route('/status')
    def status():
        """Endpoint para verificar status da API"""
        logger.info("📊 Verificando status da API...")
        
        try:
            # Teste rápido da API
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "OK"}],
                max_tokens=5
            )
            connection_ok = True
            logger.info("✅ Teste de conexão OK")
        except Exception as e:
            connection_ok = False
            logger.error(f"❌ Teste de conexão falhou: {e}")
        
        status_info = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "openai_connection": "OK" if connection_ok else "ERROR",
            "api_key_configured": bool(api_key),
            "server_status": "RUNNING"
        }
        
        return jsonify(status_info)
    
    @app.route('/extract', methods=['POST'])
    def extract_route():
        """Rota principal para extração de dados de cupons"""
        logger.info("📥 Nova requisição de extração recebida")
        
        try:
            file_bytes, filename = _read_file_storage_to_bytes()
            if not file_bytes:
                logger.warning("⚠️ Requisição sem arquivo ou imagem")
                return "❌ Erro: Nenhum arquivo ou imagem recebida.", 400
            
            logger.info(f"📁 Arquivo recebido: {filename} ({len(file_bytes)} bytes)")
            
            images = _load_image_from_bytes(file_bytes)
            
            if images:
                logger.info(f"🖼️ {len(images)} imagem(ns) carregada(s), processando primeira...")
                
                # Processar primeira imagem para IA
                processed_img = _preprocess_image_for_ai(images[0])
                img_buffer = io.BytesIO()
                processed_img.save(img_buffer, format='PNG', quality=95)
                image_bytes = img_buffer.getvalue()
                
                logger.info(f"🔄 Imagem processada: {len(image_bytes)} bytes")
                
                # Análise com IA
                ai_result = _ai_analyze_image(image_bytes)
                
                if ai_result and "erro" not in ai_result:
                    logger.info("✅ Análise bem-sucedida!")
                    formatted_text = _format_cupom_data(ai_result)
                    return formatted_text
                else:
                    error_msg = ai_result.get("erro", "Erro desconhecido") if ai_result else "Falha na análise"
                    logger.warning(f"⚠️ Erro na análise: {error_msg}")
                    return f"❌ {error_msg}"
            else:
                logger.error("❌ Falha ao carregar imagem")
                return "❌ Erro: Não foi possível carregar a imagem.", 400
                
        except Exception as e:
            logger.error(f"❌ ERRO CRÍTICO na rota /extract: {e}")
            return f"❌ Erro interno: {str(e)}", 500
    
    logger.info("🚀 Iniciando servidor...")
    app.run(host='0.0.0.0', port=5000, debug=True)
    
except Exception as e:
    print(f"❌ ERRO: {e}")
    import traceback
    traceback.print_exc()
