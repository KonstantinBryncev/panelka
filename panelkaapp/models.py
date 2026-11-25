from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Название колонки")

    class Meta:
        verbose_name = "Колонка"
        verbose_name_plural = "Колонки"

    def __str__(self):
        return self.name


# Таблица для хранения данных VPS-серверов
class VPSServer(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название сервера (например, Основной VPS)")
    host = models.CharField(max_length=100, verbose_name="IP адрес VPS")
    port = models.IntegerField(default=22, verbose_name="Порт SSH")
    user = models.CharField(max_length=50, default="root", verbose_name="Пользователь SSH")
    password = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Пароль SSH (оставьте пустым для входа по ключу)"
    )

    class Meta:
        verbose_name = "VPS Сервер"
        verbose_name_plural = "VPS Серверы"

    def __str__(self):
        return f"{self.name} ({self.host})"


class ScriptItem(models.Model):
    TYPE_CHOICES = [
        ('local', 'Локальный файл (.bat / .py)'),
        ('vps', 'Команда на VPS (SSH)'),
    ]

    title = models.CharField(max_length=100, verbose_name="Название кнопки")
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='scripts',
        verbose_name="Колонка"
    )
    action_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default='local',
        verbose_name="Где выполнять"
    )

    # Для локальных скриптов
    file_path = models.CharField(max_length=500, blank=True, verbose_name="Путь к локальному файлу")

    # Выбор сервера из выпадающего списка и команда
    server = models.ForeignKey(
        VPSServer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="VPS Сервер (если выбрана команда на VPS)"
    )
    vps_command = models.TextField(blank=True, verbose_name="Команда для выполнения на VPS")

    # Запрос параметра перед запуском
    ask_input = models.BooleanField(default=False, verbose_name="Запрашивать параметр перед запуском?")
    input_prompt = models.CharField(
        max_length=200,
        default="Вставьте ссылку на GitHub репозиторий:",
        blank=True,
        verbose_name="Текст вопроса"
    )

    class Meta:
        verbose_name = "Скрипт / Команда"
        verbose_name_plural = "Скрипты и Команды"

    def __str__(self):
        return f"{self.title} ({self.get_action_type_display()})"
