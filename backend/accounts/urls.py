"""URLs of the account and session API."""

from django.urls import URLPattern, path

from . import views

urlpatterns: list[URLPattern] = [
    path("setup/", views.SetupView.as_view(), name="setup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("language/", views.LanguageView.as_view(), name="language"),
    path("password/", views.PasswordChangeView.as_view(), name="password"),
    path("username/", views.UsernameChangeView.as_view(), name="username"),
]
