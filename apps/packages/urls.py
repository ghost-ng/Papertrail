"""URL configuration for packages app."""

from django.urls import path

from apps.packages import views

app_name = "packages"

urlpatterns = [
    # Package URLs
    path("", views.PackageListView.as_view(), name="package_list"),
    path("create/", views.PackageCreateView.as_view(), name="package_create"),
    path("<int:pk>/", views.PackageDetailView.as_view(), name="package_detail"),
    path("<int:pk>/edit/", views.PackageUpdateView.as_view(), name="package_update"),
    path("<int:pk>/submit/", views.PackageSubmitView.as_view(), name="package_submit"),
    path("<int:pk>/action/", views.StageActionView.as_view(), name="stage_action"),
    path("<int:package_pk>/tabs/create/", views.TabCreateView.as_view(), name="tab_create"),
    path("tabs/<int:pk>/edit/", views.TabUpdateView.as_view(), name="tab_update"),
    path("tabs/<int:tab_pk>/upload/", views.DocumentUploadView.as_view(), name="document_upload"),
    path("documents/<int:pk>/download/", views.DocumentDownloadView.as_view(), name="document_download"),

    # Workflow URLs
    path("workflows/", views.WorkflowTemplateListView.as_view(), name="workflow_list"),
    path("workflows/create/", views.WorkflowTemplateCreateView.as_view(), name="workflow_create"),
    path("workflows/<int:pk>/builder/", views.WorkflowBuilderView.as_view(), name="workflow_builder"),
    path("workflows/<int:pk>/save/", views.WorkflowSaveAPIView.as_view(), name="workflow_save"),
    path("workflows/<int:pk>/load/", views.WorkflowLoadAPIView.as_view(), name="workflow_load"),
]
