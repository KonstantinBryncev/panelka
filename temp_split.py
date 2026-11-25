import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def find_templates_dir() -> Path:
    """Ищет существующую папку templates в корне или в подпапках приложений."""
    root_tpl = BASE_DIR / "templates"
    if root_tpl.exists():
        return root_tpl
    for p in BASE_DIR.rglob("templates"):
        if "venv" not in p.parts and ".venv" not in p.parts:
            return p
    return root_tpl


TEMPLATES_DIR = find_templates_dir()
# Папку static создаём рядом с найденной папкой templates (или в корне)
STATIC_DIR = TEMPLATES_DIR.parent / "static"

FILES = {
    STATIC_DIR / "css" / "panelka.css": """body {
    background-color: #121417;
    color: #e9ecef;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.navbar {
    background-color: #1a1d21 !important;
    border-bottom: 1px solid #2c3036;
}
.card-panel {
    background-color: #1a1d21;
    border: 1px solid #2c3036;
    border-radius: 10px;
}
.card-header-panel {
    background-color: #212529;
    border-bottom: 1px solid #2c3036;
    font-weight: 600;
    color: #fff;
}
.terminal-box {
    background-color: #0d0f12;
    color: #00ff66;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 0.85rem;
    padding: 15px;
    border-radius: 8px;
    border: 1px solid #2c3036;
    height: 320px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
}
.form-select-dark, .form-control-dark {
    background-color: #212529;
    color: #fff;
    border: 1px solid #3a3f47;
}
.form-select-dark:focus, .form-control-dark:focus {
    background-color: #262b30;
    color: #fff;
    border-color: #198754;
    box-shadow: 0 0 0 0.2rem rgba(25, 135, 84, 0.25);
}
.project-row {
    background-color: #212529;
    border: 1px solid #2c3036;
    border-radius: 6px;
    padding: 8px 12px;
    margin-bottom: 8px;
}
""",

    STATIC_DIR / "js" / "panelka.js": """let quickTargetProject = null;
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
    const envFile = envInput.files && envInput.files.length > 0 ? envInput.files : null;

    if (!serverId) return alert('Выберите VPS сервер из базы!');
    if (!projectName) return alert('Выберите проект для запуска!');

    if (wizardModalInstance) wizardModalInstance.hide();
    runDeployRequest(serverId, projectName, envFile);
}

// --- 4. ОТПРАВКА ЗАПРОСА НА ЗАПУСК С ПОТОКОВЫМ ЧТЕНИЕМ ЛОГОВ ---
async function runDeployRequest(serverId, projectName, envFile) {
    clearTerminal();
    appendTerminal(`>>> Подготовка к запуску проекта "${projectName}"...\\n`);

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
        appendTerminal(`\\n[ОШИБКА СЕТИ]: ${err}\\n`);
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
            appendTerminal(`[ОШИБКА]: ${data.error}\\n`);
            return;
        }

        clearTerminal();
        if (action === 'logs') {
            appendTerminal(`=== ЛОГИ SCREEN: ${projectName} ===\\n${data.logs}\\n`);
        } else {
            appendTerminal(`>>> ${data.message}\\n`);
            loadVpsProjects();
        }
    } catch (e) {
        appendTerminal(`\\n[ОШИБКА]: ${e}\\n`);
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

// --- ИНИЦИАЛИЗАЦИЯ ПРИ ЗАГРУЗКЕ СТРАНИЦЫ ---
document.addEventListener('DOMContentLoaded', () => {
    loadVpsProjects();

    const quickInput = document.getElementById('quickEnvFileInput');
    if (quickInput) {
        quickInput.addEventListener('change', function () {
            if (this.files && this.files.length > 0 && quickTargetProject) {
                runDeployRequest(getSelectedServerId(), quickTargetProject, this.files);
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
                    window.location.reload();
                    return;
                }

                const data = await resp.json();
                if (data.status === 'error') return alert(data.message);

                if (data.status === 'github_deploy') {
                    document.getElementById('ghScriptId').value = data.script_id;
                    document.getElementById('ghUsernameInput').value = data.github_user || '';
                    if (!githubModalInstance) {
                        githubModalInstance = new mdb.Modal(document.getElementById('githubDeployModal'));
                    }
                    githubModalInstance.show();
                    if (data.github_user) reloadGithubRepos();
                } else if (data.status === 'vps_ready') {
                    clearTerminal();
                    const streamResp = await fetch(`/execute-vps/${data.script_id}/`);
                    const reader = streamResp.body.getReader();
                    const decoder = new TextDecoder('utf-8');
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        appendTerminal(decoder.decode(value, { stream: true }));
                    }
                }
            } catch (err) {
                console.error(err);
                window.location.reload();
            }
        });
    });
});
""",

    TEMPLATES_DIR / "base.html": """{% load static %}
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Panelka — Управление{% endblock %}</title>
    <link href="https://cloudflare.com" rel="stylesheet"/>
    <link href="https://cloudflare.com" rel="stylesheet"/>
    <link href="{% static 'css/panelka.css' %}" rel="stylesheet"/>
</head>
<body>

    {% include 'partials/navbar.html' %}

    <div class="container-fluid px-4">
        {% if messages %}
            {% for message in messages %}
                <div class="alert alert-{{ message.tags|default:'info' }} alert-dismissible fade show" role="alert">
                    {{ message }}
                    <button type="button" class="btn-close" data-mdb-dismiss="alert" aria-label="Close"></button>
                </div>
            {% endfor %}
        {% endif %}

        {% block content %}{% endblock %}
    </div>

    {% include 'partials/modals.html' %}

    <script src="https://cloudflare.com"></script>
    <script src="{% static 'js/panelka.js' %}"></script>
</body>
</html>
""",

    TEMPLATES_DIR / "index.html": """{% extends 'base.html' %}

{% block content %}
<div class="row g-4">
    <div class="col-lg-8">
        <div class="row g-3">
            {% for category in categories %}
                <div class="col-md-6">
                    <div class="card card-panel h-100">
                        <div class="card-header card-header-panel">{{ category.name }}</div>
                        <div class="card-body d-flex flex-column gap-2">
                            {% for script in category.scripts.all %}
                                <form method="post" action="{% url 'run_script' script.id %}" class="script-form" data-script-id="{{ script.id }}">
                                    {% csrf_token %}
                                    <button type="submit" class="btn btn-success w-100 text-start d-flex justify-content-between align-items-center">
                                        <span>{{ script.title }}</span>
                                        <i class="fas fa-play small"></i>
                                    </button>
                                </form>
                            {% empty %}
                                <p class="text-muted small mb-0">Кнопок пока нет</p>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            {% empty %}
                <div class="col-12">
                    <div class="alert alert-secondary">Колонок пока нет. Добавьте их в админке Django.</div>
                </div>
            {% endfor %}
        </div>
    </div>

    {% include 'partials/vps_sidebar.html' %}
</div>

{% include 'partials/terminal.html' %}
{% endblock %}
""",

    TEMPLATES_DIR / "partials" / "vps_sidebar.html": """<div class="col-lg-4">
    <div class="card card-panel mb-3">
        <div class="card-header card-header-panel d-flex justify-content-between align-items-center">
            <span><i class="fas fa-layer-group text-success me-2"></i>Проекты в screen</span>
            <button class="btn btn-sm btn-outline-secondary" onclick="loadVpsProjects()" title="Обновить">
                <i class="fas fa-sync-alt"></i>
            </button>
        </div>
        <div class="card-body" id="runningScreensList">
            <div class="text-muted small">Загрузка списка...</div>
        </div>
    </div>

    <div class="card card-panel">
        <div class="card-header card-header-panel d-flex justify-content-between align-items-center">
            <span><i class="fas fa-folder-open text-info me-2"></i>Скачанные проекты VPS</span>
            <button class="btn btn-sm btn-outline-secondary" onclick="loadVpsProjects()" title="Обновить">
                <i class="fas fa-sync-alt"></i>
            </button>
        </div>
        <div class="card-body" id="downloadedProjectsList">
            <div class="text-muted small">Загрузка списка...</div>
        </div>
    </div>
</div>

<input type="file" id="quickEnvFileInput" accept=".env,text/plain,*" style="display: none;">
""",

    TEMPLATES_DIR / "partials" / "terminal.html": """<div class="card card-panel mt-4 mb-5" id="consoleCard">
    <div class="card-header card-header-panel d-flex justify-content-between align-items-center">
        <span><i class="fas fa-terminal text-success me-2"></i>Консоль выполнения VPS</span>
        <div class="d-flex gap-2">
            <button class="btn btn-sm btn-outline-warning" onclick="clearTerminal()">Очистить</button>
            <button class="btn btn-sm btn-outline-danger" onclick="hideTerminal()">✕ Закрыть</button>
        </div>
    </div>
    <div class="card-body">
        <div class="terminal-box" id="vpsTerminal">Ожидание запуска задачи...</div>
    </div>
</div>
""",

    TEMPLATES_DIR / "partials" / "modals.html": """<!-- МОДАЛЬНОЕ ОКНО: Пошаговый запуск проекта -->
<div class="modal fade" id="wizardLaunchModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content bg-dark text-light border-secondary">
            <div class="modal-header border-secondary">
                <h5 class="modal-title"><i class="fas fa-rocket text-success me-2"></i>Запуск проекта на VPS</h5>
                <button type="button" class="btn-close btn-close-white" data-mdb-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <div class="mb-3">
                    <label class="form-label fw-bold text-info">1. Выберите VPS сервер из базы:</label>
                    <select id="wizardServerSelect" class="form-select form-select-dark" onchange="fetchProjectsForWizard()">
                        {% for s in servers %}
                            <option value="{{ s.id }}">{{ s.name }} ({{ s.host }})</option>
                        {% empty %}
                            <option value="">Серверы не добавлены в админке</option>
                        {% endfor %}
                    </select>
                </div>

                <div class="mb-3">
                    <label class="form-label fw-bold text-info">2. Выберите скачанный проект (/root/projects):</label>
                    <select id="wizardProjectSelect" class="form-select form-select-dark">
                        <option value="">Загрузка списка проектов...</option>
                    </select>
                    <div id="wizardProjectHelp" class="form-text text-muted small"></div>
                </div>

                <div class="mb-3">
                    <label class="form-label fw-bold text-info">3. Выберите локальный файл .env:</label>
                    <input type="file" id="wizardEnvInput" class="form-control form-control-dark" accept=".env,text/plain,*">
                    <div class="form-text text-muted small">
                        Если файл не выбран, проект запустится с текущим .env на сервере (или без него).
                    </div>
                </div>
            </div>
            <div class="modal-footer border-secondary">
                <button type="button" class="btn btn-secondary" data-mdb-dismiss="modal">Отмена</button>
                <button type="button" class="btn btn-success" onclick="submitWizardLaunch()">
                    <i class="fas fa-play me-1"></i> Запустить проект
                </button>
            </div>
        </div>
    </div>
</div>

<!-- МОДАЛЬНОЕ ОКНО: Клонирование с GitHub -->
<div class="modal fade" id="githubDeployModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content bg-dark text-light border-secondary">
            <div class="modal-header border-secondary">
                <h5 class="modal-title"><i class="fab fa-github me-2"></i>Клонировать с GitHub на VPS</h5>
                <button type="button" class="btn-close btn-close-white" data-mdb-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <input type="hidden" id="ghScriptId">
                <div class="mb-3">
                    <label class="form-label">Логин GitHub:</label>
                    <div class="input-group">
                        <input type="text" id="ghUsernameInput" class="form-control form-control-dark" placeholder="username">
                        <button class="btn btn-outline-info" type="button" onclick="reloadGithubRepos()">Загрузить</button>
                    </div>
                </div>
                <div class="mb-3">
                    <label class="form-label">Выберите репозиторий:</label>
                    <select id="ghRepoSelect" class="form-select form-select-dark"></select>
                </div>
                <div class="mb-3">
                    <label class="form-label">Выберите VPS сервер из базы:</label>
                    <select id="ghServerSelect" class="form-select form-select-dark"></select>
                </div>
            </div>
            <div class="modal-footer border-secondary">
                <button type="button" class="btn btn-secondary" data-mdb-dismiss="modal">Отмена</button>
                <button type="button" class="btn btn-success" onclick="startGithubClone()">Клонировать</button>
            </div>
        </div>
    </div>
</div>
""",
}


def main():
    print(f"Папка шаблонов: {TEMPLATES_DIR}")
    print(f"Папка статики:  {STATIC_DIR}\n")

    old_index = TEMPLATES_DIR / "index.html"
    if old_index.exists():
        backup_index = TEMPLATES_DIR / "index.html.bak"
        backup_index.write_text(old_index.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[BACKUP] Создана копия старого шаблона -> {backup_index.relative_to(BASE_DIR)}")

    for path, content in FILES.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"[OK] Создан файл: {path.relative_to(BASE_DIR)}")

    if STATIC_DIR == BASE_DIR / "static":
        for settings_file in BASE_DIR.rglob("settings.py"):
            if "venv" not in settings_file.parts and ".venv" not in settings_file.parts:
                text = settings_file.read_text(encoding="utf-8")
                if "STATICFILES_DIRS" not in text:
                    text += "\nSTATICFILES_DIRS = [BASE_DIR / 'static']\n"
                    settings_file.write_text(text, encoding="utf-8")
                    print(f"\n[SETTINGS] Добавлено STATICFILES_DIRS в {settings_file.relative_to(BASE_DIR)}")

    print("\nГотово! Перезапустите сервер Django (runserver) и обновите страницу с Ctrl+F5.")


if __name__ == "__main__":
    main()


