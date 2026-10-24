from django.contrib import admin

from .models import Event, Registration, Ticket


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "start_time",
        "capacity",
        "tickets_sold",
        "status",
    )
    list_filter = ("status", "category")
    search_fields = ("name", "location")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("tickets_sold", "created_at", "updated_at")
    date_hierarchy = "start_time"


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "quantity", "status", "created_at")
    list_filter = ("status", "event")
    search_fields = ("user__username", "event__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("code", "event", "user", "status", "issued_at", "checked_in_at")
    list_filter = ("status", "event")
    search_fields = ("code", "user__username", "event__name")
    readonly_fields = ("code", "issued_at")
