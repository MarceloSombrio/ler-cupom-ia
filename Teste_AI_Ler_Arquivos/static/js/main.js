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

function showResult(data) {
	resultPre.textContent = JSON.stringify(data, null, 2);
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
	return response.json();
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
	resultSection.hidden = true;
	showResult({ status: 'Processando...' });
	try {
		const json = await postFormData(formData);
		showResult(json);
	} catch (err) {
		showResult({ error: String(err) });
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
