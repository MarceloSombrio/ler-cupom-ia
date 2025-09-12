import os
import io
import re
import base64
from typing import Dict, Any, List, Optional, Tuple

from flask import Flask, render_template, request, jsonify
from PIL import Image
import numpy as np
import pytesseract
from openai import OpenAI

try:
	import cv2  # type: ignore
except Exception:
	cv2 = None

from pdf2image import convert_from_bytes

# Configure tesseract path for Windows
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
if not TESSERACT_CMD:
	# Try common Windows installation paths
	possible_paths = [
		r"C:\Users\marcelo.sombrio\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
		r"C:\Program Files\Tesseract-OCR\tesseract.exe",
		r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
	]
	for path in possible_paths:
		if os.path.exists(path):
			TESSERACT_CMD = path
			break

if TESSERACT_CMD:
	pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
	print(f"Tesseract configurado: {TESSERACT_CMD}")
else:
	print("AVISO: Tesseract não encontrado. Instale em: https://github.com/UB-Mannheim/tesseract/wiki")

# Configure OpenAI
OPENAI_API_KEY = "sk-myTqtiPzxyxkmRmU0C6o-lW5ekaHrnChi2lvDBPKk6T3BlbkFJTeEtH5pt0ymMcpXlNQfjXkF6-Z-_l-omSWbQmjwPoA"
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


# ------------------------
# OCR and Extraction
# ------------------------

def _ocr_image(pil_image: Image.Image) -> str:
	config = "--oem 3 --psm 6"
	try:
		# Try Portuguese first
		text = pytesseract.image_to_string(pil_image, lang='por', config=config)
		if not text.strip():
			raise Exception("Portuguese OCR returned empty")
	except Exception:
		# Fallback to English if Portuguese fails
		try:
			text = pytesseract.image_to_string(pil_image, lang='eng', config=config)
		except Exception:
			# Last resort: no language specified
			text = pytesseract.image_to_string(pil_image, config=config)
	return text


def _detect_brand(full_text: str) -> str:
	text = full_text.upper()
	# Clean text for better matching
	clean_text = re.sub(r'[^\w\s]', ' ', text)
	clean_text = re.sub(r'\s+', ' ', clean_text)
	
	# ZE DELIVERY patterns
	ze_patterns = ["ZÉ DELIVERY", "ZE DELIVERY", "ZE\u0301 DELIVERY", "ZÉ-DELIVERY", "ZÉDELIVERY", "ZEDELIVERY"]
	if any(k in clean_text for k in ze_patterns):
		return "ZE DELIVERY"
	
	# IFOOD patterns (more flexible)
	ifood_patterns = ["IFOOD", "I-FOOD", "I FOOD", "IFOOD", "IFOOD", "IFOOD", "IFOOD"]
	if any(k in clean_text for k in ifood_patterns):
		return "IFOOD"
	
	# Additional checks for common OCR errors
	if "FOOD" in clean_text and ("I" in clean_text or "1" in clean_text):
		return "IFOOD"
	
	return "Aplicativo Proprio"


def _extract_datetime(full_text: str) -> Optional[str]:
	text = full_text
	lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
	
	# First, look for "Criado Em:" pattern
	for ln in lines:
		if "CRIADO EM:" in ln.upper():
			# Extract date/time after "Criado Em:"
			date_patterns = [
				r"(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
				r"(\d{4}[\-/]\d{1,2}[\-/]\d{1,2})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
			]
			for pat in date_patterns:
				m = re.search(pat, ln)
				if m:
					date_part, time_part = m.group(1), m.group(2)
					return f"{date_part} {time_part}"
	
	# Fallback: look for any date/time pattern in the text
	patterns = [
		# 12/09/2025 14:33 or 12-09-2025 14:33:59
		r"(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
		# 2025-09-12 14:33
		r"(\d{4}[\-/]\d{1,2}[\-/]\d{1,2})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
	]
	for pat in patterns:
		m = re.search(pat, text)
		if m:
			date_part, time_part = m.group(1), m.group(2)
			# Normalize
			return f"{date_part} {time_part}"
	return None


def _extract_delivery_fee(full_text: str) -> Optional[str]:
	text = full_text.upper()
	lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
	money_patterns = [
		r"R\$\s*\d+[.,]?\d{0,3}[.,]\d{2}",
		r"\d+[.,]?\d{0,3}[.,]\d{2}",
	]
	
	# Priority keywords (delivery-related first)
	priority_keywords = ["TAXA DE ENTREGA", "TAXA ENTREGA", "FRETE", "ENTREGA"]
	secondary_keywords = ["SERVIÇO", "SERVICO", "TAXA DE SERVIÇO", "TAXA DE SERVICO"]
	
	# First pass: look for delivery-related fees
	for ln in lines:
		if any(kw in ln for kw in priority_keywords):
			for pat in money_patterns:
				m = re.search(pat, ln)
				if m:
					val = m.group(0)
					if not val.startswith("R$"):
						val = "R$ " + val
					return val.replace(" ", "")
	
	# Second pass: look for service fees if no delivery fee found
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


def _extract_pickup_location(full_text: str) -> Optional[str]:
	text = full_text
	lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
	candidates: List[str] = []
	
	# Look for address patterns first (more reliable)
	addr_patterns = [
		r"(RUA|AV\.|AVENIDA|ROD\.|RODOVIA|AL\.|ALAMEDA|ESTRADA|TRAV\.|TRAVESSA)\s+[^,]+(?:,\s*\d+)?(?:,\s*[^,]+)?",
		r"Endereço:\s*([^,\n]+(?:,\s*[^,\n]+)*)",
	]
	
	for ln in lines:
		for pattern in addr_patterns:
			match = re.search(pattern, ln, re.IGNORECASE)
			if match:
				addr = match.group(1) if match.groups() else match.group(0)
				# Clean up the address
				addr = re.sub(r'[^\w\s,.-]', '', addr)  # Remove special chars except basic punctuation
				addr = re.sub(r'\s+', ' ', addr).strip()  # Normalize spaces
				if len(addr) > 10:  # Reasonable address length
					candidates.append(addr)
	
	# Fallback: look for keywords
	keywords = ["RETIRADA", "RETIRE", "LOJA", "ESTABELECIMENTO", "LOCAL DE RETIRADA", "ENDEREÇO", "ENDERECO", "PONTO DE RETIRADA"]
	for i, ln in enumerate(lines):
		upper_ln = ln.upper()
		if any(kw in upper_ln for kw in keywords):
			# Clean the line
			clean_ln = re.sub(r'[^\w\s,.-]', '', ln)
			clean_ln = re.sub(r'\s+', ' ', clean_ln).strip()
			if len(clean_ln) > 10:
				candidates.append(clean_ln)
			if i + 1 < len(lines):
				next_ln = re.sub(r'[^\w\s,.-]', '', lines[i + 1])
				next_ln = re.sub(r'\s+', ' ', next_ln).strip()
				if len(next_ln) > 10:
					candidates.append(next_ln)
	
	# Choose the best candidate (longest reasonable address)
	candidates = [c for c in candidates if 10 <= len(c) <= 200]
	if candidates:
		candidates.sort(key=len, reverse=True)
		return candidates[0]
	return None


def _ai_analyze_image(image_bytes: bytes) -> Dict[str, Any]:
	"""Use OpenAI GPT-4o-mini to analyze image directly"""
	try:
		# Convert image to base64
		base64_string = base64.b64encode(image_bytes).decode('utf-8')
		
		response = client.chat.completions.create(
			model="gpt-4o-mini",
			messages=[
				{
					"role": "system", 
					"content": "Você é um especialista em análise de cupons fiscais. Extraia os dados solicitados e responda APENAS em formato JSON."
				},
				{
					"role": "user", 
					"content": [
						{
							"type": "text", 
							"text": """Analise este cupom fiscal e extraia APENAS estas informações em formato JSON:

{
  "marca": "ZE DELIVERY", "IFOOD" ou "Aplicativo Proprio",
  "data_hora": "data e hora do pedido (formato: DD/MM/AAAA HH:MM)",
  "frete_ou_taxa": "valor da taxa de entrega em R$ (ex: R$5,50)"
}

REGRAS:
- Se encontrar "ZÉ DELIVERY" ou "ZE DELIVERY" → marca = "ZE DELIVERY"
- Se encontrar "IFOOD" ou "I-FOOD" → marca = "IFOOD"  
- Caso contrário → marca = "Aplicativo Proprio"
- Para data/hora, procure por "Criado Em:" primeiro, depois qualquer data/hora
- Para frete, procure por "taxa de entrega", "frete", "entrega" (não taxa de serviço)
- Se não encontrar alguma informação, use null
- Responda APENAS com o JSON, sem explicações"""
						},
						{
							"type": "image_url", 
							"image_url": {"url": f"data:image/png;base64,{base64_string}"}
						}
					]
				}
			],
			max_tokens=200,
			temperature=0.1
		)
		
		ai_result = response.choices[0].message.content.strip()
		# Try to parse JSON response
		import json
		return json.loads(ai_result)
		
	except Exception as e:
		print(f"Erro na análise AI da imagem: {e}")
		return None


def _ai_enhance_extraction(text: str) -> Dict[str, Any]:
	"""Use OpenAI to enhance the extraction with AI analysis (fallback)"""
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
		# Try to parse JSON response
		import json
		return json.loads(ai_result)
		
	except Exception as e:
		print(f"Erro na análise AI: {e}")
		return None


def extract_all(text: str, image_bytes: bytes = None) -> Dict[str, Any]:
	# Always get OCR result first
	ocr_result = {
		"marca": _detect_brand(text),
		"data_hora": _extract_datetime(text),
		"frete_ou_taxa": _extract_delivery_fee(text),
	}
	
	# Check if AI should be disabled
	use_ai = request.args.get('noai') != 'true'
	
	if use_ai and image_bytes:
		# Try AI image analysis first (most accurate)
		ai_image_result = _ai_analyze_image(image_bytes)
		if ai_image_result:
			# Return both results with AI image as primary
			result = {
				"ia_imagem": ai_image_result,
				"ocr": ocr_result,
				"metodo": "IA_IMAGEM + OCR"
			}
		else:
			# Try AI text enhancement as fallback
			ai_text_result = _ai_enhance_extraction(text)
			if ai_text_result:
				result = {
					"ia_texto": ai_text_result,
					"ocr": ocr_result,
					"metodo": "IA_TEXTO + OCR"
				}
			else:
				# AI failed, return OCR only
				result = ocr_result
				result["metodo"] = "OCR"
	elif use_ai:
		# Try AI text enhancement only
		ai_text_result = _ai_enhance_extraction(text)
		if ai_text_result:
			result = {
				"ia_texto": ai_text_result,
				"ocr": ocr_result,
				"metodo": "IA_TEXTO + OCR"
			}
		else:
			result = ocr_result
			result["metodo"] = "OCR"
	else:
		# Use OCR only
		result = ocr_result
		result["metodo"] = "OCR"
	
	# Add debug info if requested
	if request.args.get('debug') == 'true':
		result["debug"] = {
			"texto_ocr": text[:500] + "..." if len(text) > 500 else text,
			"linhas": text.splitlines()[:10]  # First 10 lines
		}
	
	return result


# ------------------------
# Routes
# ------------------------

@app.get('/')
def index():
	return render_template('index.html')


@app.post('/extract')
def extract_route():
	file_bytes, filename = _read_file_storage_to_bytes()
	if not file_bytes:
		return jsonify({"error": "Nenhum arquivo ou imagem recebida."}), 400
	try:
		images = _load_image_from_bytes(file_bytes)
		overall_text_parts: List[str] = []
		for img in images:
			pre = _preprocess_image_for_ocr(img)
			ocr_text = _ocr_image(pre)
			overall_text_parts.append(ocr_text)
		full_text = "\n".join(overall_text_parts)
		
		# For AI image analysis, use the first image
		first_image_bytes = None
		if images:
			# Convert first image to bytes for AI analysis
			img_buffer = io.BytesIO()
			images[0].save(img_buffer, format='PNG')
			first_image_bytes = img_buffer.getvalue()
		
		data = extract_all(full_text, first_image_bytes)
		return jsonify({"ok": True, "data": data})
	except Exception as e:
		return jsonify({"error": f"Falha ao processar arquivo: {str(e)}"}), 500


if __name__ == '__main__':
	port = int(os.getenv('PORT', '5000'))
	app.run(host='0.0.0.0', port=port, debug=True)
