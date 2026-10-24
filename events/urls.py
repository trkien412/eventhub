from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.EventListView.as_view(), name="home"),
    path("events/", views.EventListView.as_view(), name="event_list"),
    path("events/<slug:slug>/", views.EventDetailView.as_view(), name="detail"),
    path("events/<slug:slug>/register/", views.register_event, name="register"),
    path("tickets/", views.my_registrations, name="my_registrations"),
    path(
        "tickets/registrations/<int:pk>/cancel/",
        views.cancel_my_registration,
        name="cancel_registration",
    ),
]
