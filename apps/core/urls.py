"""URL configuration for core app."""

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.UserDashboardView.as_view(), name="home"),
    path("dashboard/", views.UserDashboardView.as_view(), name="dashboard"),
    path("toggle-dark-mode/", views.ToggleDarkModeView.as_view(), name="toggle_dark_mode"),
]
