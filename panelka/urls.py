from django.contrib import admin
from django.urls import path
from panelkaapp.views import (
    index,
    run_script,
    get_github_repos,
    execute_github_deploy,
    execute_vps_stream,
    vps_projects_list,
    deploy_with_env,
    screen_control,
    execute_custom_ssh,
    execute_local_stream,
)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', index, name='index'),
    path('run/<int:script_id>/', run_script, name='run_script'),
    path('github-repos/<int:script_id>/', get_github_repos, name='get_github_repos'),
    path('execute-github/<int:script_id>/', execute_github_deploy, name='execute_github_deploy'),
    path('execute-vps/<int:script_id>/', execute_vps_stream, name='execute_vps_stream'),
    path('vps-projects/', vps_projects_list, name='vps_projects_list'),
    path('deploy-with-env/', deploy_with_env, name='deploy_with_env'),
    path('screen-control/', screen_control, name='screen_control'),
    path('execute-custom-ssh/', execute_custom_ssh, name='execute_custom_ssh'),
    path('execute-local/<int:script_id>/', execute_local_stream, name='execute_local_stream'),  
]
