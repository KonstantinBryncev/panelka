let quickTargetProject = null;
let wizardModalInstance = null;
let githubModalInstance = null;

function getSelectedServerId() {
	const el = document.getElementById('globalServerSelect');
	return el ? el.value : '';
}

function appendTerminal(text) {
	const card = document.getElementById('consoleCard');
	const term = document.getElementById('vpsTerminal');
	card.style.display = 'block';
	term.textContent += text;
	term.scrollTop = term.scrollHeight;
}

function clearTerminal() {
	document.getElementById('vpsTerminal').textContent = '';
}

function hideTerminal() {
	document.getElementById('consoleCard').style.display = 'none';
}

// --- 1. ЗАГРУЗКА СПИСКА ПРОЕКТОВ И SCREEN ДЛЯ ВЫБРАННОГО СЕРВЕРА ---
async function loadVpsProjects() {
	const serverId = getSelectedServerId();
	const runningBox = document.getElementById('runningScreensList');
	const projectsBox = document.getElementById('downloadedProjectsList');

	if (!serverId) {
		runningBox.innerHTML = '<div class="text-warning small">Добавьте VPS сервер в админке.</div>';
		projectsBox.innerHTML = '<div class="text-warning small">Добавьте VPS сервер в админке.</div>';
		return;
	}

	runningBox.innerHTML = '<div class="text-muted small">Подключение к серверу...</div>';
	projectsBox.innerHTML = '<div class="text-muted small">Подключение к серверу...</div>';

	try {
		const resp = await fetch(`/vps-projects/?server_id=${encodeURIComponent(serverId)}`);
		const data = await resp.json();

		if (!resp.ok || data.error) {
			const err = data.error || 'Ошибка загрузки';
			runningBox.innerHTML = `<div class="text-danger small">${err}</div>`;
			projectsBox.innerHTML = `<div class="text-danger small">${err}</div>`;
			return;
		}

		if (data.running && data.running.length > 0) {
			runningBox.innerHTML = data.running.map(name => `
				<div class="project-row d-flex justify-content-between align-items-center flex-wrap gap-2">
					<span class="fw-semibold text-success"><i class="fas fa-circle small me-1"></i>${name}</span>
					<div class="btn-group btn-group-sm">
						<button class="btn btn-outline-info" onclick="controlScreen('logs', '${name}')">Консоль</button>
						<button class="btn btn-outline-warning" onclick="controlScreen('restart', '${name}')">Рестарт</button>
						<button class="btn btn-outline-danger" onclick="controlScreen('stop', '${name}')">Остановить</button>
					</div>
				</div>
			`).join('');
		} else {
			runningBox.innerHTML = '<div class="text-muted small">Нет активных screen-сессий</div>';
		}

		if (data.projects && data.projects.length > 0) {
			projectsBox.innerHTML = data.projects.map(name => `
				<div class="project-row d-flex justify-content-between align-items-center flex-wrap gap-2">
					<span class="fw-semibold"><i class="fas fa-folder text-warning me-1"></i>${name}</span>
					<div class="btn-group btn-group-sm">
						<button class="btn btn-success" onclick="triggerQuickEnvLaunch('${name}')">Выбрать .env и запустить</button>
						<button class="btn btn-outline-light" onclick="runDeployRequest(getSelectedServerId(), '${name}', null)">Запустить без .env</button>
					</div>
				</div>
			`).join('');
		} else {
			projectsBox.innerHTML = '<div class="text-muted small">Папка /root/projects пуста</div>';
		}
	} catch (e) {
		runningBox.innerHTML = `<div class="text-danger small">Ошибка сети: ${e}</div>`;
		projectsBox.innerHTML = `<div class="text-danger small">Ошибка сети: ${e}</div>`;
	}
}

// --- 2. БЫСТРЫЙ ВЫБОР .ENV ИЗ СПИСКА ПРОЕКТОВ ---
function triggerQuickEnvLaunch(projectName) {
	quickTargetProject = projectName;
	const input = document.getElementById('quickEnvFileInput');
	input.value = '';
	input.click();
}

// --- 3. ПОШАГОВОЕ МОДАЛЬНОЕ ОКНО: СЕРВЕР -> ПРОЕКТ -> .ENV -> ЗАПУСК ---
function openWizardLaunchModal() {
	const globalSrv = getSelectedServerId();
	const wizardSrvSelect = document.getElementById('wizardServerSelect');
	if (globalSrv) {
		wizardSrvSelect.value = globalSrv;
	}
	document.getElementById('wizardEnvInput').value = '';

	if (!wizardModalInstance) {
		wizardModalInstance = new mdb.Modal(document.getElementById('wizardLaunchModal'));
	}
	wizardModalInstance.show();
	fetchProjectsForWizard();
}

async function fetchProjectsForWizard() {
	const serverId = document.getElementById('wizardServerSelect').value;
	const projectSelect = document.getElementById('wizardProjectSelect');
	const helpEl = document.getElementById('wizardProjectHelp');

	if (!serverId) {
		projectSelect.innerHTML = '<option value="">Сначала выберите сервер</option>';
		return;
	}

	const globalSelect = document.getElementById('globalServerSelect');
	if (globalSelect && globalSelect.value !== serverId) {
		globalSelect.value = serverId;
		loadVpsProjects();
	}

	projectSelect.innerHTML = '<option value="">Загрузка списка проектов с VPS...</option>';
	helpEl.textContent = '';

	try {
		const resp = await fetch(`/vps-projects/?server_id=${encodeURIComponent(serverId)}`);
		const data = await resp.json();

		if (!resp.ok || data.error) {
			projectSelect.innerHTML = '<option value="">Ошибка подключения к VPS</option>';
			helpEl.textContent = data.error || 'Не удалось получить список папок';
			return;
		}

		if (data.projects && data.projects.length > 0) {
			projectSelect.innerHTML = data.projects.map(p => `<option value="${p}">${p}</option>`).join('');
			helpEl.textContent = `Найдено проектов: ${data.projects.length}`;
		} else {
			projectSelect.innerHTML = '<option value="">Нет скачанных проектов в /root/projects</option>';
			helpEl.textContent = 'Сначала клонируйте репозиторий на этот сервер.';
		}
	} catch (e) {
		projectSelect.innerHTML = '<option value="">Ошибка сети</option>';
		helpEl.textContent = String(e);
	}
}

function submitWizardLaunch() {
	const serverId = document.getElementById('wizardServerSelect').value;
	const projectName = document.getElementById('wizardProjectSelect').value;
	const envInput = document.getElementById('wizardEnvInput');
	const envFile = envInput.files[0] && envInput.files.length > 0 ? envInput.files : null;

	if (!serverId) return alert('Выберите VPS сервер из базы!');
	if (!projectName) return alert('Выберите проект для запуска!');

	if (wizardModalInstance) wizardModalInstance.hide();
	runDeployRequest(serverId, projectName, envFile);
}

// --- 4. ОТПРАВКА ЗАПРОСА НА ЗАПУСК С ПОТОКОВЫМ ЧТЕНИЕМ ЛОГОВ ---
async function runDeployRequest(serverId, projectName, envFile) {
	clearTerminal();
	appendTerminal(`>>> Подготовка к запуску проекта "${projectName}"...\n`);

	const formData = new FormData();
	formData.append('server_id', serverId);
	formData.append('project_name', projectName);
	if (envFile) {
		formData.append('env_file', envFile);
	}

	try {
		const response = await fetch('/deploy-with-env/', {
			method: 'POST',
			body: formData
		});

		const reader = response.body.getReader();
		const decoder = new TextDecoder('utf-8');

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			appendTerminal(decoder.decode(value, { stream: true }));
		}

		loadVpsProjects();
	} catch (err) {
		appendTerminal(`\n[ОШИБКА СЕТИ]: ${err}\n`);
	}
}

// --- 5. УПРАВЛЕНИЕ SCREEN ---
async function controlScreen(action, projectName) {
	const serverId = getSelectedServerId();
	const formData = new FormData();
	formData.append('server_id', serverId);
	formData.append('action', action);
	formData.append('project_name', projectName);

	try {
		const resp = await fetch('/screen-control/', {
			method: 'POST',
			body: formData
		});
		const data = await resp.json();

		if (data.error) {
			clearTerminal();
			appendTerminal(`[ОШИБКА]: ${data.error}\n`);
			return;
		}

		clearTerminal();
		if (action === 'logs') {
			appendTerminal(`=== ЛОГИ SCREEN: ${projectName} ===\n${data.logs}\n`);
		} else {
			appendTerminal(`>>> ${data.message}\n`);
			loadVpsProjects();
		}
	} catch (e) {
		appendTerminal(`\n[ОШИБКА]: ${e}\n`);
	}
}

// --- 6. GITHUB ДЕПЛОЙ ---
async function reloadGithubRepos() {
	const scriptId = document.getElementById('ghScriptId').value;
	const username = document.getElementById('ghUsernameInput').value.trim();
	const repoSelect = document.getElementById('ghRepoSelect');
	const srvSelect = document.getElementById('ghServerSelect');

	repoSelect.innerHTML = '<option>Загрузка репозиториев...</option>';
	const resp = await fetch(`/github-repos/${scriptId}/?username=${encodeURIComponent(username)}`);
	const data = await resp.json();

	if (data.error) {
		repoSelect.innerHTML = `<option>${data.error}</option>`;
		return;
	}

	repoSelect.innerHTML = data.repos.map(r => `<option value="${r.clone_url}" data-name="${r.name}">${r.name}</option>`).join('');
	srvSelect.innerHTML = data.servers.map(s => `<option value="${s.id}">${s.name} (${s.host})</option>`).join('');

	const currentGlobalSrv = getSelectedServerId();
	if (currentGlobalSrv) srvSelect.value = currentGlobalSrv;
}

async function startGithubClone() {
	const scriptId = document.getElementById('ghScriptId').value;
	const repoSelect = document.getElementById('ghRepoSelect');
	const selectedOption = repoSelect.options[repoSelect.selectedIndex];
	const repoUrl = selectedOption.value;
	const repoName = selectedOption.getAttribute('data-name');
	const serverId = document.getElementById('ghServerSelect').value;

	if (githubModalInstance) githubModalInstance.hide();
	clearTerminal();

	const url = `/execute-github/${scriptId}/?server_id=${encodeURIComponent(serverId)}&repo_url=${encodeURIComponent(repoUrl)}&repo_name=${encodeURIComponent(repoName)}`;
	const resp = await fetch(url);
	const reader = resp.body.getReader();
	const decoder = new TextDecoder('utf-8');

	while (true) {
		const { done, value } = await reader.read();
		if (done) break;
		appendTerminal(decoder.decode(value, { stream: true }));
	}
	loadVpsProjects();
}

// --- 7. ВЫПОЛНЕНИЕ ПРОИЗВОЛЬНОЙ SSH КОМАНДЫ ИЗ КОНСОЛИ ---
function sendQuickSshCommand(cmd) {
	const input = document.getElementById('customSshInput');
	if (input) {
		input.value = cmd;
		runCustomSshCommand();
	}
}

async function runCustomSshCommand() {
	const input = document.getElementById('customSshInput');
	const command = input ? input.value.trim() : '';
	const serverId = getSelectedServerId();

	if (!serverId) return alert('Сначала выберите VPS сервер вверху страницы!');
	if (!command) return alert('Введите команду!');

	clearTerminal();

	const formData = new FormData();
	formData.append('server_id', serverId);
	formData.append('command', command);

	try {
		const resp = await fetch('/execute-custom-ssh/', {
			method: 'POST',
			body: formData
		});
		const reader = resp.body.getReader();
		const decoder = new TextDecoder('utf-8');

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			appendTerminal(decoder.decode(value, { stream: true }));
		}
	} catch (err) {
		appendTerminal(`\n[ОШИБКА СЕТИ]: ${err}\n`);
	}
}

// --- ИНИЦИАЛИЗАЦИЯ ПРИ ЗАГРУЗКЕ СТРАНИЦЫ ---
document.addEventListener('DOMContentLoaded', () => {
	loadVpsProjects();

	const quickInput = document.getElementById('quickEnvFileInput');
	if (quickInput) {
		quickInput.addEventListener('change', function () {
			if (this.files && this.files.length > 0 && quickTargetProject) {
				runDeployRequest(getSelectedServerId(), quickTargetProject, this.files[0]);
			}
		});
	}

	document.querySelectorAll('.script-form').forEach(form => {
		form.addEventListener('submit', async function (e) {
			e.preventDefault();
			const formData = new FormData(this);

			try {
				const resp = await fetch(this.action, {
					method: 'POST',
					body: formData,
					headers: { 'X-Requested-With': 'XMLHttpRequest' }
				});

				const contentType = resp.headers.get('content-type') || '';
				if (!contentType.includes('application/json')) {
					const errText = await resp.text();
					clearTerminal();
					appendTerminal(`[ОШИБКА СЕРВЕРА ${resp.status}]:\n${errText.slice(0, 800)}\n`);
					return;
				}

				const data = await resp.json();
				if (data.status === 'error') {
					clearTerminal();
					appendTerminal(`[ОШИБКА]: ${data.message}\n`);
					return;
				}

				if (data.status === 'github_deploy') {
					document.getElementById('ghScriptId').value = data.script_id;
					document.getElementById('ghUsernameInput').value = data.github_user || '';
					if (!githubModalInstance) {
						githubModalInstance = new mdb.Modal(document.getElementById('githubDeployModal'));
					}
					githubModalInstance.show();
					if (data.github_user) reloadGithubRepos();
				} else if (data.status === 'vps_ready') {
					const params = new URLSearchParams();
					const currentSrv = getSelectedServerId();
					if (currentSrv) params.append('server_id', currentSrv);

					if (data.ask_input) {
						const val = prompt(data.input_prompt || `Введите данные для "${data.title}":`);
						if (val === null) return;
						params.append('user_input', val);
					}

					const matches = [...(data.commands || '').matchAll(/\{\{\s*([a-zA-Z0-9_а-яА-Я]+)\s*\}\}/g)];
					const varNames = [...new Set(matches.map(m => m).filter(v => v !== 'input'))];

					for (const vName of varNames) {
						const val = prompt(`Введите значение для "${vName}":`);
						if (val === null) return;
						params.append(`input_${vName}`, val);
					}

					clearTerminal();
					const query = params.toString() ? `?${params.toString()}` : '';
					const streamResp = await fetch(`/execute-vps/${data.script_id}/${query}`);
					const reader = streamResp.body.getReader();
					const decoder = new TextDecoder('utf-8');
					while (true) {
						const { done, value } = await reader.read();
						if (done) break;
						appendTerminal(decoder.decode(value, { stream: true }));
					}
					loadVpsProjects();

				} else if (data.status === 'local_py_ready') {
					const params = new URLSearchParams();
					const prompts = data.prompts || [];

					for (let i = 0; i < prompts.length; i++) {
						const label = prompts[i] || `Введите параметр #${i + 1}:`;
						const val = prompt(label);
						if (val === null) return;
						params.append(`ans_${i}`, val);
					}

					clearTerminal();
					const query = params.toString() ? `?${params.toString()}` : '';
					const streamResp = await fetch(`/execute-local/${data.script_id}/${query}`);
					const reader = streamResp.body.getReader();
					const decoder = new TextDecoder('utf-8');

					while (true) {
						const { done, value } = await reader.read();
						if (done) break;
						appendTerminal(decoder.decode(value, { stream: true }));
					}
				} else if (data.status === 'bat_started') {
					clearTerminal();
					appendTerminal(`>>> ${data.message}\n`);
				}
			} catch (err) {
				console.error(err);
				window.location.reload();
			}
		});
	});
});

