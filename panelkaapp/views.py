import os
import re
import sys
import subprocess
import urllib.parse
import urllib.request
import json
import paramiko

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Category, ScriptItem, VPSServer


def get_selected_server(request):
	"""Возвращает выбранный сервер из базы по server_id (из GET или POST) или первый доступный."""
	server_id = request.GET.get('server_id') or request.POST.get('server_id')
	if server_id:
		srv = VPSServer.objects.filter(id=server_id).first()
		if srv:
			return srv
	return VPSServer.objects.first()


def ssh_connect(client, srv, timeout=15):
	"""Универсальное подключение к VPSServer независимо от названия поля логина (user/username/login)."""
	login_user = (
		getattr(srv, 'user', None)
		or getattr(srv, 'username', None)
		or getattr(srv, 'login', None)
		or 'root'
	)
	port = getattr(srv, 'port', 22) or 22
	password = getattr(srv, 'password', None)
	key_filename = getattr(srv, 'ssh_key_path', None) or getattr(srv, 'key_path', None)

	connect_kwargs = {
		'hostname': srv.host,
		'port': port,
		'username': login_user,
		'timeout': timeout,
	}
	if password:
		connect_kwargs['password'] = password
	if key_filename and os.path.exists(key_filename):
		connect_kwargs['key_filename'] = key_filename

	client.connect(**connect_kwargs)


def index(request):
	categories = Category.objects.prefetch_related('scripts').all()
	servers = VPSServer.objects.all()
	return render(request, 'index.html', {
		'categories': categories,
		'servers': servers,
	})


def run_script(request, script_id):
	if request.method == 'POST':
		script = get_object_or_404(ScriptItem, id=script_id)
		action = (script.action_type or '').upper()

		# 1. Если выбран режим выполнения на VPS (учитываем любые варианты action_type или наличие vps_command)
		if 'VPS' in action or (script.vps_command and not script.file_path):
			srv = script.server or get_selected_server(request)
			if not srv:
				return JsonResponse({'status': 'error', 'message': 'Не выбран VPS сервер ни в кнопке, ни в шапке!'}, status=400)
			return JsonResponse({
				'status': 'vps_ready',
				'script_id': script.id,
				'server_id': srv.id,
				'title': script.title,
				'server_name': str(srv),
				'commands': script.vps_command or '',
				'ask_input': bool(script.ask_input),
				'input_prompt': script.input_prompt or '',
			})

		# 2. Обычный локальный запуск (.py стримим во внутреннюю консоль, .bat открываем в окне Windows)
		file_path = (script.file_path or '').strip().strip('"')
		if not file_path:
			return JsonResponse({
				'status': 'error',
				'message': f'У кнопки "{script.title}" (action_type={script.action_type}) не заполнены ни file_path, ни vps_command!'
			}, status=400)

		if not os.path.exists(file_path):
			return JsonResponse({'status': 'error', 'message': f'Файл не найден: {file_path}'}, status=400)

		if file_path.lower().endswith('.py'):
			try:
				with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
					code_text = f.read()
				prompts = re.findall(r'input\(\s*["\']([^"\']*)["\']\s*\)', code_text)
			except Exception:
				prompts = []

			return JsonResponse({
				'status': 'local_py_ready',
				'script_id': script.id,
				'title': script.title,
				'prompts': prompts,
			})

		try:
			subprocess.Popen(
				['cmd.exe', '/c', file_path],
				creationflags=subprocess.CREATE_NEW_CONSOLE,
				cwd=os.path.dirname(file_path)
			)
			return JsonResponse({'status': 'bat_started', 'message': f'Скрипт "{script.title}" запущен в окне CMD!'})
		except Exception as e:
			return JsonResponse({'status': 'error', 'message': f'Ошибка запуска: {e}'}, status=500)

	return redirect('index')




# --- ПОТОКОВЫЙ ЗАПУСК ЛОКАЛЬНОГО .PY СКРИПТА ВО ВНУТРЕННЮЮ КОНСОЛЬ ---
def execute_local_stream(request, script_id):
	script = get_object_or_404(ScriptItem, id=script_id)
	raw_file = (
		getattr(script, 'file_path', None)
		or getattr(script, 'local_path', None)
		or getattr(script, 'script_path', None)
		or getattr(script, 'path', None)
		or getattr(script, 'file', None)
	)
	if not raw_file:
		return StreamingHttpResponse(["[ОШИБКА]: У кнопки не указан путь к файлу!\n"])

	file_path = raw_file.path if hasattr(raw_file, 'path') else str(raw_file).strip().strip('"')
	if not os.path.exists(file_path):
		return StreamingHttpResponse([f"[ОШИБКА]: Файл не найден: {file_path}\n"])


	# Собираем ответы на input() из GET-параметров (?ans_0=...&ans_1=...)
	answers = []
	idx = 0
	while f'ans_{idx}' in request.GET:
		answers.append(request.GET.get(f'ans_{idx}', ''))
		idx += 1

	def event_stream():
		try:
			yield f"=== Запуск локального скрипта: {script.title} ===\n\n"
			env = os.environ.copy()
			env['PYTHONIOENCODING'] = 'utf-8'
			env['PYTHONUNBUFFERED'] = '1'

			proc = subprocess.Popen(
				[sys.executable, '-u', file_path],
				stdin=subprocess.PIPE,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				cwd=os.path.dirname(file_path),
				env=env,
				text=True,
				encoding='utf-8',
				errors='replace',
				bufsize=1
			)

			# Передаём ответы для input() в stdin процесса
			if answers and proc.stdin:
				proc.stdin.write('\n'.join(answers) + '\n')
				proc.stdin.flush()
				proc.stdin.close()

			for line in iter(proc.stdout.readline, ''):
				yield line

			proc.wait()
			yield f"\n=== ВЫПОЛНЕНИЕ ЗАВЕРШЕНО (код: {proc.returncode}) ===\n"
		except Exception as e:
			yield f"\n[ОШИБКА]: {str(e)}\n"

	return StreamingHttpResponse(event_stream(), content_type='text/plain; charset=utf-8')



# --- ПОЛУЧЕНИЕ СПИСКА РЕПОЗИТОРИЕВ GITHUB ---
def get_github_repos(request, script_id):
	script = get_object_or_404(ScriptItem, id=script_id)
	username = request.GET.get('username') or script.github_user

	if not username:
		return JsonResponse({'error': 'Не указан логин GitHub!'}, status=400)

	api_host = ".".join(["api", "github", "com"])
	endpoint = "/".join(["users", urllib.parse.quote(username), "repos"])
	url = f"https://{api_host}/{endpoint}?per_page=100&sort=updated"
	req = urllib.request.Request(url, headers={'User-Agent': 'Panelka-App'})

	try:
		with urllib.request.urlopen(req, timeout=10) as response:
			data = json.loads(response.read().decode('utf-8'))
			repos = [
				{
					'name': repo['name'],
					'clone_url': repo['clone_url'],
					'private': repo['private'],
					'description': repo['description'] or ''
				}
				for repo in data
			]
	except Exception as e:
		return JsonResponse({'error': f'Ошибка GitHub API: {str(e)}'}, status=400)

	servers = [
		{
			'id': s.id,
			'name': s.name,
			'host': s.host,
			'username': getattr(s, 'user', None) or getattr(s, 'username', 'root'),
		}
		for s in VPSServer.objects.all()
	]
	return JsonResponse({
		'username': username,
		'repos': repos,
		'servers': servers,
	})


# --- ЗАПУСК КЛОНИРОВАНИЯ НА ВЫБРАННОМ VPS (ТОЛЬКО СКАЧИВАНИЕ) ---
def execute_github_deploy(request, script_id):
	server_id = request.GET.get('server_id')
	repo_url = request.GET.get('repo_url')
	repo_name = request.GET.get('repo_name')

	srv = get_object_or_404(VPSServer, id=server_id)
	target_dir = f"/root/projects/{repo_name}"

	def event_stream():
		client = paramiko.SSHClient()
		client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		try:
			yield f"=== Подключение к {srv.host} ===\n"
			ssh_connect(client, srv, timeout=15)

			commands = (
				f"mkdir -p /root/projects && "
				f"if [ -d '{target_dir}' ]; then "
				f"  echo '>>> Папка уже существует. Обновляю (git pull)...' && cd '{target_dir}' && git pull; "
				f"else "
				f"  echo '>>> Клонирую репозиторий...' && git clone '{repo_url}' '{target_dir}'; "
				f"fi && "
				f"echo '>>> Готово! Проект сохранен в {target_dir}'"
			)

			stdin, stdout, stderr = client.exec_command(commands, get_pty=True)
			for line in iter(stdout.readline, ""):
				clean_line = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line)
				yield clean_line

			yield "\n=== СКАЧИВАНИЕ ЗАВЕРШЕНО ===\n"
		except Exception as e:
			yield f"\n[ОШИБКА]: {str(e)}\n"
		finally:
			client.close()

	return StreamingHttpResponse(event_stream(), content_type='text/plain; charset=utf-8')


# --- ВЫПОЛНЕНИЕ ОБЫЧНЫХ VPS СКРИПТОВ ---
def execute_vps_stream(request, script_id):
	script = get_object_or_404(ScriptItem, id=script_id)
	srv = script.server or get_selected_server(request)

	user_inputs = {}
	for key, value in request.GET.items():
		if key.startswith('input_'):
			var_name = key.replace('input_', '')
			user_inputs[var_name] = value

	single_input = request.GET.get('user_input', '')

	def event_stream():
		if not srv:
			yield "[ОШИБКА]: VPS сервер не найден!\n"
			return
		client = paramiko.SSHClient()
		client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		try:
			yield f"=== [{srv.name}] Подключение к {srv.host}... ===\n"
			ssh_connect(client, srv, timeout=15)
			yield "=== Успешно! Запуск команд... ===\n\n"

			raw_commands = (script.vps_command or '').replace('\r\n', '\n')
			for var_name, val in user_inputs.items():
				raw_commands = raw_commands.replace(f"{{{{{var_name}}}}}", val)
			if single_input:
				raw_commands = raw_commands.replace('{input}', single_input).replace('{{input}}', single_input)

			stdin, stdout, stderr = client.exec_command(raw_commands, get_pty=True)
			for line in iter(stdout.readline, ""):
				clean_line = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line)
				yield clean_line

			yield "\n=== ВЫПОЛНЕНИЕ ЗАВЕРШЕНО ===\n"
		except Exception as e:
			yield f"\n[ОШИБКА]: {str(e)}\n"
		finally:
			client.close()

	return StreamingHttpResponse(event_stream(), content_type='text/plain; charset=utf-8')


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ПОИСКА ПАПКИ ПРОЕКТА НА VPS ---
def resolve_project_dir(client, project_name):
	"""Находит полный путь к папке проекта по его имени."""
	if project_name.startswith('/'):
		return project_name
	cmd = (
		f"find \"$HOME\" /root /opt /srv /var/www /home -maxdepth 5 -type d -name '{project_name}' "
		f"! -path '*/.*' ! -path '*/venv*' ! -path '*/.venv*' 2>/dev/null | head -n 1"
	)
	stdin, stdout, stderr = client.exec_command(cmd)
	found = stdout.read().decode('utf-8').strip()
	return found or f"/root/projects/{project_name}"


def vps_projects_list(request):
	srv = get_selected_server(request)
	if not srv:
		return JsonResponse({'error': 'Нет доступных VPS серверов в базе!'}, status=400)

	client = paramiko.SSHClient()
	client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	try:
		ssh_connect(client, srv, timeout=10)

		# Простой и надежный поиск папок в /root/projects и в домашней директории
		cmd = (
			"mkdir -p /root/projects 2>/dev/null; "
			"ls -1 /root/projects 2>/dev/null; "
			"ls -1 -d /root/*/ /home/*/*/ 2>/dev/null | xargs -r -n1 basename | grep -Ev '^(projects|snap|venv|\\.venv)$'"
		)
		stdin, stdout, stderr = client.exec_command(cmd)
		raw_out = stdout.read().decode('utf-8')
		folders = sorted(set(f.strip() for f in raw_out.splitlines() if f.strip()))

		# Живые screen сессии
		stdin, stdout, stderr = client.exec_command("screen -wipe >/dev/null 2>&1 || true; screen -ls")
		screen_out = stdout.read().decode('utf-8')
		running_screens = []
		for line in screen_out.splitlines():
			if 'Dead' in line:
				continue
			match = re.search(r'\d+\.([^\s]+)', line)
			if match:
				running_screens.append(match.group(1))

		return JsonResponse({
			'server_id': srv.id,
			'server_name': str(srv),
			'projects': folders,
			'running': running_screens
		})
	except Exception as e:
		return JsonResponse({'error': str(e)}, status=500)
	finally:
		client.close()

# --- ВЫПОЛНЕНИЕ ПРОИЗВОЛЬНОЙ SSH КОМАНДЫ НА ВЫБРАННОМ VPS ---
@csrf_exempt
def execute_custom_ssh(request):
	if request.method != 'POST':
		return JsonResponse({'error': 'Только POST'}, status=405)

	srv = get_selected_server(request)
	if not srv:
		return StreamingHttpResponse(["[ОШИБКА]: VPS сервер не выбран!\n"])

	command = request.POST.get('command', '').strip()
	if not command:
		return StreamingHttpResponse(["[ОШИБКА]: Введите команду!\n"])

	def event_stream():
		client = paramiko.SSHClient()
		client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		try:
			yield f"=== [{srv.name} | {srv.host}] $ {command} ===\n"
			ssh_connect(client, srv, timeout=15)
			stdin, stdout, stderr = client.exec_command(command, get_pty=True)
			for line in iter(stdout.readline, ""):
				clean_line = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line)
				yield clean_line
			yield "\n=== ГОТОВО ===\n"
		except Exception as e:
			yield f"\n[ОШИБКА]: {str(e)}\n"
		finally:
			client.close()

	return StreamingHttpResponse(event_stream(), content_type='text/plain; charset=utf-8')




# --- ЗАПУСК ПРОЕКТА В SCREEN (С .ENV ИЛИ БЕЗ НЕГО) НА ВЫБРАННОМ VPS ---
@csrf_exempt
def deploy_with_env(request):
	if request.method != 'POST':
		return JsonResponse({'error': 'Только POST'}, status=405)

	srv = get_selected_server(request)
	if not srv:
		return StreamingHttpResponse(["[ОШИБКА]: Выбранный VPS сервер не найден в базе!\n"])

	project_name = request.POST.get('project_name')
	if not project_name:
		return StreamingHttpResponse(["[ОШИБКА]: Не указано имя проекта!\n"])

	env_file = request.FILES.get('env_file')

	def event_stream():
		client = paramiko.SSHClient()
		client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		try:
			yield f"=== Сервер: {srv.name} ({srv.host}) ===\n"
			yield "=== Подключение к серверу... ===\n"
			ssh_connect(client, srv, timeout=15)

			target_dir = resolve_project_dir(client, project_name)
			yield f">>> Рабочая папка: {target_dir}\n"

			# 1. Если передан .env файл — загружаем его на сервер по SFTP
			if env_file:
				yield f">>> Загрузка файла {env_file.name} -> {target_dir}/.env ...\n"
				sftp = client.open_sftp()
				with sftp.file(f"{target_dir}/.env", 'wb') as remote_file:
					for chunk in env_file.chunks():
						remote_file.write(chunk)
				sftp.close()
				yield ">>> Файл .env успешно загружен!\n"
			else:
				yield ">>> Запуск без загрузки нового .env...\n"

			# 2. Установка зависимостей и запуск в screen с записью вывода в screen.log
			commands = (
				f"cd '{target_dir}' && "
				f"echo '>>> Проверка/создание виртуального окружения...' && "
				f"if [ ! -d 'venv' ] && [ ! -d '.venv' ]; then python3 -m venv venv; fi && "
				f"VENV_ACT=$([ -f '.venv/bin/activate' ] && echo '.venv/bin/activate' || echo 'venv/bin/activate') && "
				f"source \"$VENV_ACT\" && "
				f"if [ -f 'requirements.txt' ]; then echo '>>> Установка зависимостей...' && pip install -r requirements.txt; fi && "
				f"echo '>>> Перезапуск screen-сессии {project_name}...' && "
				f"screen -S '{project_name}' -X quit 2>/dev/null || true && "
				f"screen -wipe >/dev/null 2>&1 || true && "
				f"MAIN_FILE=$(ls manage.py main.py bot.py app.py run.py run_*.py 2>/dev/null | head -n 1) && "
				f"if [ \"$MAIN_FILE\" = \"manage.py\" ]; then "
				f"  screen -dmS '{project_name}' bash -c 'cd {target_dir} && source '$VENV_ACT' && python manage.py migrate && python manage.py runserver 0.0.0.0:8000 > screen.log 2>&1'; "
				f"elif [ -n \"$MAIN_FILE\" ]; then "
				f"  screen -dmS '{project_name}' bash -c 'cd {target_dir} && source '$VENV_ACT' && python '$MAIN_FILE' > screen.log 2>&1'; "
				f"else "
				f"  echo '[ОШИБКА]: Не найден исполняемый файл (main.py, bot.py, app.py, manage.py)'; exit 1; "
				f"fi && "
				f"sleep 1 && screen -ls"
			)

			stdin, stdout, stderr = client.exec_command(commands, get_pty=True)
			for line in iter(stdout.readline, ""):
				clean_line = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line)
				yield clean_line

			yield f"\n=== ПРОЕКТ {project_name} ЗАПУЩЕН В ФОНЕ (SCREEN) ===\n"
		except Exception as e:
			yield f"\n[ОШИБКА]: {str(e)}\n"
		finally:
			client.close()

	return StreamingHttpResponse(event_stream(), content_type='text/plain; charset=utf-8')


# --- УПРАВЛЕНИЕ SCREEN (ЛОГИ, РЕСТАРТ, ОСТАНОВКА) НА ВЫБРАННОМ VPS ---
@csrf_exempt
def screen_control(request):
	if request.method != 'POST':
		return JsonResponse({'error': 'Только POST'}, status=405)

	srv = get_selected_server(request)
	if not srv:
		return JsonResponse({'error': 'Нет доступных VPS серверов!'}, status=400)

	action = request.POST.get('action')
	project_name = request.POST.get('project_name')

	client = paramiko.SSHClient()
	client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	try:
		ssh_connect(client, srv, timeout=10)
		target_dir = resolve_project_dir(client, project_name)

		if action == 'stop':
			client.exec_command(f"screen -S '{project_name}' -X quit 2>/dev/null || true; screen -wipe >/dev/null 2>&1 || true")
			return JsonResponse({'status': 'ok', 'message': f'Проект {project_name} остановлен.'})

		elif action == 'logs':
			tmp_log = f"/tmp/screen_log_{project_name}.txt"
			# Сначала читаем screen.log из папки проекта, если его нет — пробуем hardcopy живой сессии
			cmd = (
				f"if [ -f '{target_dir}/screen.log' ]; then "
				f"  tail -n 60 '{target_dir}/screen.log'; "
				f"else "
				f"  screen -S '{project_name}' -X hardcopy {tmp_log} >/dev/null 2>&1 && cat {tmp_log} && rm -f {tmp_log} || echo 'Лог-файл пуст или сессия не активна.'; "
				f"fi"
			)
			stdin, stdout, stderr = client.exec_command(cmd)
			logs = stdout.read().decode('utf-8', errors='replace')
			lines = [l for l in logs.splitlines() if l.strip()]
			return JsonResponse({'status': 'ok', 'logs': '\n'.join(lines[-60:]) or 'Лог пуст.'})

		elif action == 'restart':
			cmd = (
				f"screen -S '{project_name}' -X quit 2>/dev/null || true && "
				f"screen -wipe >/dev/null 2>&1 || true && "
				f"cd '{target_dir}' && "
				f"VENV_ACT=$([ -f '.venv/bin/activate' ] && echo '.venv/bin/activate' || echo 'venv/bin/activate') && "
				f"MAIN_FILE=$(ls main.py bot.py app.py run.py manage.py 2>/dev/null | head -n 1) && "
				f"if [ \"$MAIN_FILE\" = \"manage.py\" ]; then "
				f"  screen -dmS '{project_name}' bash -c 'cd {target_dir} && source '$VENV_ACT' && python manage.py runserver 0.0.0.0:8000 > screen.log 2>&1'; "
				f"elif [ -n \"$MAIN_FILE\" ]; then "
				f"  screen -dmS '{project_name}' bash -c 'cd {target_dir} && source '$VENV_ACT' && python '$MAIN_FILE' > screen.log 2>&1'; "
				f"fi"
			)
			client.exec_command(cmd)
			return JsonResponse({'status': 'ok', 'message': f'Проект {project_name} перезапущен!'})

		return JsonResponse({'error': 'Неизвестное действие'}, status=400)
	except Exception as e:
		return JsonResponse({'error': str(e)}, status=500)
	finally:
		client.close()


