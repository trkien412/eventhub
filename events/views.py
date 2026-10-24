from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from .forms import EventFilterForm, RegistrationForm
from .models import Event, Registration
from .services import RegistrationError, cancel_registration, register_for_event


class EventListView(ListView):
    model = Event
    template_name = "events/event_list.html"
    context_object_name = "events"
    paginate_by = 9

    def get_queryset(self):
        queryset = Event.objects.public().select_related("created_by")
        # Khi mở trang lần đầu (không có query string), form chưa "bound" nên
        # is_valid() = False và bộ lọc mặc định không được áp dụng. Truyền
        # time=upcoming để danh sách mặc định không lẫn sự kiện đã kết thúc.
        query = self.request.GET or {"time": "upcoming"}
        form = EventFilterForm(query)
        self.filter_form = form

        if form.is_valid():
            data = form.cleaned_data
            now = timezone.now()
            if data.get("q"):
                queryset = queryset.filter(
                    Q(name__icontains=data["q"])
                    | Q(location__icontains=data["q"])
                    | Q(description__icontains=data["q"])
                )
            if data.get("category"):
                queryset = queryset.filter(category=data["category"])
            if data.get("date"):
                queryset = queryset.filter(start_time__date=data["date"])
            time_filter = data.get("time") or "upcoming"
            if time_filter == "upcoming":
                queryset = queryset.filter(end_time__gte=now)
            elif time_filter == "past":
                queryset = queryset.filter(end_time__lt=now).order_by("-start_time")
        self.filtered_queryset = queryset
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        upcoming = Event.objects.public().filter(end_time__gte=now)
        context["filter_form"] = self.filter_form
        context["featured_event"] = (
            self.filtered_queryset.filter(end_time__gte=now)
            .order_by("start_time")
            .first()
            or self.filtered_queryset.first()
        )
        context["public_stats"] = {
            "upcoming": upcoming.count(),
            "open": Event.objects.public()
            .filter(
                registration_start__lte=now,
                registration_end__gte=now,
                start_time__gt=now,
                tickets_sold__lt=F("capacity"),
            )
            .count(),
            "remaining": upcoming.aggregate(
                total=Sum(F("capacity") - F("tickets_sold"))
            )["total"]
            or 0,
        }
        context["page_title"] = "Khám phá sự kiện"
        context["active_nav"] = "events"
        return context


class EventDetailView(DetailView):
    model = Event
    template_name = "events/event_detail.html"
    context_object_name = "event"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        queryset = Event.objects.select_related("created_by")
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return queryset
        return queryset.public()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.object
        context["page_title"] = event.name
        context["registration_form"] = RegistrationForm(event=event)
        existing_registration = None
        if self.request.user.is_authenticated:
            existing_registration = (
                Registration.objects.filter(user=self.request.user, event=event)
                .prefetch_related("tickets")
                .first()
            )
        context["existing_registration"] = existing_registration
        context["confirmed_count"] = event.registrations.filter(
            status=Registration.Status.CONFIRMED
        ).aggregate(total=Count("id"))["total"]
        context["active_nav"] = "events"
        return context


@login_required
@require_POST
def register_event(request, slug):
    event = get_object_or_404(Event.objects.public(), slug=slug)
    form = RegistrationForm(request.POST, event=event)
    if not form.is_valid():
        error = next(iter(form.errors.values()))[0]
        messages.error(request, error)
        return redirect(event.get_absolute_url())

    try:
        registration = register_for_event(
            user=request.user,
            event_id=event.pk,
            quantity=form.cleaned_data["quantity"],
        )
    except RegistrationError as exc:
        messages.error(request, str(exc))
        return redirect(event.get_absolute_url())

    messages.success(
        request,
        f"Đăng ký thành công {registration.quantity} vé cho “{event.name}”. "
        "Mã vé đã được tạo trong mục Vé của tôi.",
    )
    return redirect("events:my_registrations")


@login_required
def my_registrations(request):
    registrations = (
        Registration.objects.filter(user=request.user)
        .select_related("event")
        .prefetch_related("tickets")
        .order_by("-created_at")
    )
    stats = registrations.aggregate(
        total=Count("id"),
        confirmed=Count("id", filter=Q(status=Registration.Status.CONFIRMED)),
        cancelled=Count("id", filter=Q(status=Registration.Status.CANCELLED)),
    )
    return render(
        request,
        "events/my_registrations.html",
        {
            "registrations": registrations,
            "stats": stats,
            "page_title": "Vé của tôi",
            "active_nav": "tickets",
        },
    )


@login_required
@require_POST
def cancel_my_registration(request, pk):
    registration = get_object_or_404(
        Registration, pk=pk, user=request.user
    )
    try:
        cancel_registration(
            registration_id=registration.pk, actor=request.user, by_staff=False
        )
    except RegistrationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Đã hủy đăng ký và hủy các vé tương ứng.")
    return redirect("events:my_registrations")
