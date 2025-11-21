"""
URL configuration for dashboard_site project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from dashboard_app.views import (
    accreditation_sync_view,
    dashboard_view,
    login_view,
    logout_view,
    mail_inbox_view,
    mail_sent_view,
    mail_view_view,
    notification_download_report_view,
    report_export_excel_view,
    report_view,
    send_report_notification_view,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('', dashboard_view, name='dashboard'),
    path('report/', report_view, name='report'),
    path('report/export/', report_export_excel_view, name='report_export_excel'),
    path('report/send/', send_report_notification_view, name='report_send'),
    path(
        'notifications/<int:pk>/download/',
        notification_download_report_view,
        name='notification_download',
    ),
    path('accreditation/sync/', accreditation_sync_view, name='accreditation_sync'),
    path('mail/', mail_inbox_view, name='mail_inbox'),
    path('mail/sent/', mail_sent_view, name='mail_sent'),
    path('mail/<int:pk>/', mail_view_view, name='mail_view'),
]
