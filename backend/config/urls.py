from django.urls import include, path

urlpatterns = [path("api/", include("email_generator.urls"))]