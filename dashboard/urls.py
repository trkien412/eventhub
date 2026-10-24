from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="index"),
    path("events/", views.EventManageListView.as_view(), name="event_list"),
    path("events/add/", views.EventCreateView.as_view(), name="event_add"),
    path("events/<int:pk>/edit/", views.EventUpdateView.as_view(), name="event_edit"),
    path(
        "events/<int:pk>/delete/",
        views.EventDeleteView.as_view(),
        name="event_delete",
    ),
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/<int:pk>/toggle/", views.toggle_user_active, name="user_toggle"),
    path(
        "registrations/",
        views.RegistrationListView.as_view(),
        name="registration_list",
    ),
    path(
        "registrations/<int:pk>/cancel/",
        views.cancel_registration_admin,
        name="registration_cancel",
    ),
    path("tickets/", views.TicketListView.as_view(), name="ticket_list"),
    path("tickets/<int:pk>/check-in/", views.ticket_check_in, name="ticket_check_in"),
]
