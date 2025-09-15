const form = document.getElementById('upload-form');
const fileInput = document.getElementById('file');
const resultSection = document.getElementById('result');
const resultPre = document.getElementById('result-json');

const openCameraBtn = document.getElementById('open-camera');
const closeCameraBtn = document.getElementById('close-camera');
const captureBtn = document.getElementById('capture');
const debugBtn = document.getElementById('debug-mode');
const aiBtn = document.getElementById('ai-mode');
const cameraSection = document.getElementById('camera-section');
const video = document.getElementById('video');
const canvas = document.getElementById('canvas');

let mediaStream = null;
let capturedImageBase64 = null;
let debugMode = false;
let aiMode = true; // AI enabled by default
let processingTimer = null;
let startTime = null;

function startProcessingTimer() {
	startTime = Date.now();
	let step = 0;
	const steps = [
		"📸 Processando imagem...",
		"🤖 Enviando para IA...",
		"🧠 GPT-4o-mini analisando...",
		"📊 Extraindo dados...",
		"✨ Finalizando..."
	];
	
	processingTimer = setInterval(() => {
		const elapsed = Math.floor((Date.now() - startTime) / 1000);
		const minutes = Math.floor(elapsed / 60);
		const seconds = elapsed % 60;
		const timeStr = minutes > 0 ? `${minutes}:${seconds.toString().padStart(2, '0')}` : `${seconds}s`;
		
		// Mudar step baseado no tempo
		if (elapsed < 2) step = 0;
		else if (elapsed < 4) step = 1;
		else if (elapsed < 8) step = 2;
		else if (elapsed < 12) step = 3;
		else step = 4;
		
		const dots = ".".repeat((elapsed % 3) + 1);
		
		resultPre.innerHTML = `
<div style="text-align: center; padding: 2rem;">
	<div style="font-size: 2rem; margin-bottom: 1rem;">🤖</div>
	<div style="font-size: 1.2rem; margin-bottom: 0.5rem;">${steps[step]}${dots}</div>
	<div style="color: #22c55e; font-weight: bold; font-size: 1.1rem;">⏱️ ${timeStr}</div>
	<div style="margin-top: 1rem; color: #94a3b8; font-size: 0.9rem;">
		Análise inteligente em andamento
	</div>
	<div style="margin-top: 0.5rem; color: #94a3b8; font-size: 0.8rem;">
		${elapsed < 5 ? "Processamento rápido..." : "Análise detalhada..."}
	</div>
</div>`;
	}, 100);
}

function stopProcessingTimer() {
	if (processingTimer) {
		clearInterval(processingTimer);
		processingTimer = null;
	}
}

function showResult(data) {
	stopProcessingTimer();
	
	if (typeof data === 'string') {
		resultPre.textContent = data;
	} else {
		resultPre.textContent = JSON.stringify(data, null, 2);
	}
	resultSection.hidden = false;
}

async function postFormData(formData) {
	let url = '/extract';
	const params = [];
	if (debugMode) params.push('debug=true');
	if (!aiMode) params.push('noai=true');
	if (params.length > 0) url += '?' + params.join('&');
	
	const response = await fetch(url, {
		method: 'POST',
		body: formData,
	});
	
	// Tentar como texto primeiro, depois como JSON se falhar
	const text = await response.text();
	try {
		return JSON.parse(text);
	} catch {
		return text;
	}
}

form.addEventListener('submit', async (e) => {
	e.preventDefault();
	const formData = new FormData();
	const file = fileInput.files && fileInput.files[0];
	if (file) {
		formData.append('file', file);
	} else if (capturedImageBase64) {
		formData.append('image_base64', capturedImageBase64);
	} else {
		alert('Selecione um arquivo ou capture uma imagem.');
		return;
	}
	
	resultSection.hidden = false;
	startProcessingTimer();
	
	try {
		const result = await postFormData(formData);
		showResult(result);
	} catch (err) {
		showResult(`❌ Erro: ${String(err)}`);
	}
});

openCameraBtn.addEventListener('click', async () => {
	try {
		mediaStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
		video.srcObject = mediaStream;
		cameraSection.hidden = false;
		capturedImageBase64 = null;
	} catch (err) {
		alert('Não foi possível acessar a câmera: ' + String(err));
	}
});

closeCameraBtn.addEventListener('click', () => {
	if (mediaStream) {
		mediaStream.getTracks().forEach(t => t.stop());
		mediaStream = null;
	}
	cameraSection.hidden = true;
});

captureBtn.addEventListener('click', () => {
	if (!video.videoWidth) {
		alert('Câmera ainda carregando. Tente novamente.');
		return;
	}
	canvas.width = video.videoWidth;
	canvas.height = video.videoHeight;
	const ctx = canvas.getContext('2d');
	canvas.hidden = false;
	ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
	capturedImageBase64 = canvas.toDataURL('image/jpeg', 0.92);
	alert('Imagem capturada. Agora clique em Extrair Dados.');
});

debugBtn.addEventListener('click', () => {
	debugMode = !debugMode;
	debugBtn.textContent = debugMode ? 'Debug ON' : 'Modo Debug';
	debugBtn.style.background = debugMode ? '#ef4444' : '#3b82f6';
	alert(debugMode ? 'Modo Debug ATIVADO - Mostrará o texto OCR' : 'Modo Debug DESATIVADO');
});

aiBtn.addEventListener('click', () => {
	aiMode = !aiMode;
	aiBtn.textContent = aiMode ? '🤖 AI ON' : '📝 OCR';
	aiBtn.style.background = aiMode ? '#22c55e' : '#6b7280';
	alert(aiMode ? '🤖 IA ATIVADA - Análise inteligente com OpenAI' : '📝 OCR TRADICIONAL - Análise por regex');
});
