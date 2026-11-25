from django.contrib import admin
from .models import Category, VPSServer, ScriptItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


@admin.register(VPSServer)
class VPSServerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'host', 'port', 'user')


@admin.register(ScriptItem)
class ScriptItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'category', 'action_type', 'server', 'ask_input')
    list_filter = ('category', 'action_type', 'server')
