"""URL patterns for the analyzer_ui app."""

from django.urls import path

from . import views

app_name = "analyzer_ui"

urlpatterns = [
    path("", views.AnalysisListView.as_view(), name="analysis-list"),
    path("new/", views.AnalysisCreateView.as_view(), name="analysis-create"),
    path("<uuid:pk>/", views.AnalysisDetailView.as_view(), name="analysis-detail"),
    path("<uuid:pk>/download/pdf/", views.download_pdf, name="download-pdf"),
    path(
        "<uuid:apk>/download/script/<uuid:spk>/",
        views.download_script,
        name="download-script",
    ),
    path(
        "<uuid:pk>/download/all-scripts/",
        views.download_all_scripts,
        name="download-all-scripts",
    ),
    path("<uuid:pk>/json/", views.analysis_json, name="analysis-json"),
]
