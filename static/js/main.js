const form = document.getElementById('upload-form');
const fileInput = document.getElementById('file');
const fileInputLabel = document.getElementById('file-input-label');
const resultSection = document.getElementById('result');
const resultPre = document.getElementById('result-json');

const importFileBtn = document.getElementById('import-file');
const openCameraBtn = document.getElementById('open-camera');
const closeCameraBtn = document.getElementById('close-camera');
const closeCameraModalBtn = document.getElementById('close-camera-modal');
const captureBtn = document.getElementById('capture');
const debugBtn = document.getElementById('debug-mode');
const cameraModal = document.getElementById('camera-modal');
const video = document.getElementById('video');
const canvas = document.getElementById('canvas');

let mediaStream = null;
let capturedImageBase64 = null;
let debugMode = false;
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
		// Verificar se é uma mensagem de erro
		if (data.includes('❌') || data.includes('Erro') || data.includes('não foi possível')) {
			resultPre.textContent = data;
			resultSection.hidden = false;
			
			// Resetar botões para permitir nova tentativa
			resetButtons();
		} else {
			resultPre.textContent = data;
			resultSection.hidden = false;
		}
	} else {
		resultPre.textContent = JSON.stringify(data, null, 2);
		resultSection.hidden = false;
	}
}

function resetButtons() {
	// Resetar botão da câmera
	openCameraBtn.textContent = '📷 Abrir Câmera';
	openCameraBtn.style.background = '#3b82f6';
	
	// Resetar botão de importar arquivo
	importFileBtn.textContent = '📁 Importar Arquivo';
	importFileBtn.style.background = '#3b82f6';
	
	// Limpar dados capturados
	capturedImageBase64 = null;
	fileInput.value = '';
}

async function postFormData(formData) {
	let url = '/extract';
	const params = [];
	if (debugMode) params.push('debug=true');
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

// Botão para importar arquivo
importFileBtn.addEventListener('click', () => {
	fileInput.click();
});

// Event listener para quando um arquivo é selecionado
fileInput.addEventListener('change', (e) => {
	if (e.target.files && e.target.files[0]) {
		capturedImageBase64 = null; // Limpar imagem capturada
		// Mostrar nome do arquivo selecionado
		const fileName = e.target.files[0].name;
		importFileBtn.textContent = `📁 ${fileName}`;
		importFileBtn.style.background = '#22c55e';
	}
});

// Abrir modal da câmera
openCameraBtn.addEventListener('click', async () => {
	try {
		// Mostrar modal primeiro
		cameraModal.hidden = false;
		cameraModal.style.display = 'flex';
		
		// Solicitar acesso à câmera
		mediaStream = await navigator.mediaDevices.getUserMedia({ 
			video: { facingMode: 'environment' }, 
			audio: false 
		});
		video.srcObject = mediaStream;
		capturedImageBase64 = null;
		
		// Limpar seleção de arquivo
		fileInput.value = '';
		importFileBtn.textContent = '📁 Importar Arquivo';
		importFileBtn.style.background = '#3b82f6';
	} catch (err) {
		// Se falhar, fechar modal
		cameraModal.hidden = true;
		cameraModal.style.display = 'none';
		alert('Não foi possível acessar a câmera: ' + String(err));
	}
});

// Fechar modal da câmera
function closeCameraModal() {
	if (mediaStream) {
		mediaStream.getTracks().forEach(t => t.stop());
		mediaStream = null;
	}
	cameraModal.hidden = true;
	cameraModal.style.display = 'none';
	
	// Resetar botão da câmera apenas se não há foto confirmada
	if (openCameraBtn.textContent !== '📷 Foto Confirmada!') {
		openCameraBtn.textContent = '📷 Abrir Câmera';
		openCameraBtn.style.background = '#3b82f6';
	}
}

closeCameraBtn.addEventListener('click', closeCameraModal);
closeCameraModalBtn.addEventListener('click', closeCameraModal);

// Fechar modal clicando fora dele
cameraModal.addEventListener('click', (e) => {
	if (e.target === cameraModal) {
		closeCameraModal();
	}
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
	
	// Fechar modal após captura
	closeCameraModal();
	
	// Mostrar feedback visual - foto confirmada e pronta
	openCameraBtn.textContent = '📷 Foto Confirmada!';
	openCameraBtn.style.background = '#22c55e';
	
	// Limpar seleção de arquivo
	fileInput.value = '';
	importFileBtn.textContent = '📁 Importar Arquivo';
	importFileBtn.style.background = '#3b82f6';
	
	alert('📸 Foto confirmada e pronta para extração! Clique em "✨ Extrair Dados" para processar.');
});


debugBtn.addEventListener('click', () => {
	debugMode = !debugMode;
	debugBtn.textContent = debugMode ? '🔧 Debug ON' : '🔧 Modo Debug';
	debugBtn.style.background = debugMode ? '#ef4444' : '#3b82f6';
	alert(debugMode ? 'Modo Debug ATIVADO - Mostrará o texto OCR' : 'Modo Debug DESATIVADO');
});
