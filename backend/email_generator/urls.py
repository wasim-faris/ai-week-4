from django.urls import path

from .views import generate_email_view

urlpatterns = [path("generate-email/", generate_email_view, name="generate-email")]