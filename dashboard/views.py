import logging
import uuid
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, F, Q, Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from accounts.models import User
from events.forms import EventForm
from events.models import Event, Registration, Ticket
from events.services import RegistrationError, cancel_registration, check_in_ticket

from .permissions import StaffRequiredMixin, staff_required

logger = logging.getLogger("events")


class DashboardView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        confirmed = Registration.Status.CONFIRMED

        events = Event.objects.all()
        registrations = Registration.objects.filter(status=confirmed)
        stats = {
            "events_total": events.count(),
            "events_upcoming": events.filter(
                status=Event.Status.PUBLISHED, end_time__gte=now
            ).count(),
            "events_open": events.filter(
                status=Event.Status.PUBLISHED,
                registration_start__lte=now,
                registration_end__gte=now,
                start_time__gt=now,
                tickets_sold__lt=F("capacity"),
            ).count(),
            "registrations_total": registrations.count(),
            "tickets_sold": events.aggregate(total=Sum("tickets_sold"))["total"] or 0,
            "users_total": User.objects.filter(is_active=True).count(),
            "revenue": registrations.aggregate(total=Sum("total_price"))["total"] or 0,
        }

        recent_registrations = registrations.select_related("user", "event").order_by(
            "-created_at"
        )[:8]
        top_events = Event.objects.filter(status=Event.Status.PUBLISHED).order_by(
            "-tickets_sold", "start_time"
        )[:6]

        start_day = timezone.localdate() - timedelta(days=6)
        daily_rows = (
            registrations.filter(created_at__date__gte=start_day)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        daily_map = {row["day"]: row["count"] for row in daily_rows}
        chart_days = []
        for offset in range(7):
            day = start_day + timedelta(days=offset)
            chart_days.append(
                {
                    "date": day,
                    "label": day.strftime("%d/%m"),
                    "count": daily_map.get(day, 0),
                }
            )
        max_daily = max((item["count"] for item in chart_days), default=0)
        for item in chart_days:
            item["percent"] = round(item["count"] * 100 / max_daily) if max_daily else 0

        context.update(
            {
                "stats": stats,
                "recent_registrations": recent_registrations,
                "top_events": top_events,
                "chart_days": chart_days,
                "max_daily": max_daily,
                "page_title": "Bảng điều khiển",
                "active_nav": "dashboard",
            }
        )
        return context


class EventManageListView(StaffRequiredMixin, ListView):
    model = Event
    template_name = "dashboard/event_list.html"
    context_object_name = "events"
    paginate_by = 15

    def get_queryset(self):
        queryset = Event.objects.annotate(
            reg_count=Count("registrations", distinct=True)
        ).order_by("-start_time")
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(location__icontains=q))
        if status in Event.Status.values:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "q": self.request.GET.get("q", ""),
                "selected_status": self.request.GET.get("status", ""),
                "status_choices": Event.Status.choices,
                "page_title": "Quản lý sự kiện",
                "active_nav": "events_admin",
            }
        )
        return context


class EventCreateView(StaffRequiredMixin, CreateView):
    model = Event
    form_class = EventForm
    template_name = "dashboard/event_form.html"
    success_url = reverse_lazy("dashboard:event_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Đã tạo sự kiện “{self.object.name}”.")
        logger.info(
            "event_created",
            extra={"event_id": self.object.id, "actor_id": self.request.user.id},
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {"page_title": "Thêm sự kiện", "active_nav": "events_admin", "is_edit": False}
        )
        return context


class EventUpdateView(StaffRequiredMixin, UpdateView):
    model = Event
    form_class = EventForm
    template_name = "dashboard/event_form.html"
    success_url = reverse_lazy("dashboard:event_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Đã cập nhật sự kiện “{self.object.name}”.")
        logger.info(
            "event_updated",
            extra={"event_id": self.object.id, "actor_id": self.request.user.id},
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Chỉnh sửa sự kiện",
                "active_nav": "events_admin",
                "is_edit": True,
            }
        )
        return context


class EventDeleteView(StaffRequiredMixin, DeleteView):
    model = Event
    template_name = "dashboard/event_confirm_delete.html"
    success_url = reverse_lazy("dashboard:event_list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            response = super().post(request, *args, **kwargs)
        except ProtectedError:
            messages.error(
                request,
                "Không thể xóa sự kiện đã có đăng ký/vé. Hãy giữ dữ liệu để "
                "bảo toàn lịch sử, hoặc hủy sự kiện bằng cách đổi trạng thái.",
            )
            return redirect("dashboard:event_list")
        messages.success(request, f"Đã xóa sự kiện “{self.object.name}”.")
        logger.info(
            "event_deleted",
            extra={"event_id": self.object.id, "actor_id": request.user.id},
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Xóa sự kiện", "active_nav": "events_admin"})
        return context


class UserListView(StaffRequiredMixin, ListView):
    model = User
    template_name = "dashboard/user_list.html"
    context_object_name = "users"
    paginate_by = 20

    def get_queryset(self):
        queryset = User.objects.annotate(
            reg_count=Count("registrations", distinct=True)
        ).order_by("-date_joined")
        q = self.request.GET.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone__icontains=q)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "q": self.request.GET.get("q", ""),
                "page_title": "Quản lý người dùng",
                "active_nav": "users",
            }
        )
        return context


@staff_required
@require_POST
def toggle_user_active(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        messages.error(request, "Bạn không thể tự khóa tài khoản của mình.")
        return redirect("dashboard:user_list")
    if target.is_superuser and not request.user.is_superuser:
        messages.error(request, "Chỉ superuser mới có thể khóa tài khoản superuser.")
        return redirect("dashboard:user_list")
    if target.is_superuser and target.is_active:
        active_superusers = User.objects.filter(
            is_superuser=True, is_active=True
        ).count()
        if active_superusers <= 1:
            messages.error(
                request, "Không thể khóa superuser đang hoạt động cuối cùng."
            )
            return redirect("dashboard:user_list")

    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    state = "mở khóa" if target.is_active else "khóa"
    messages.success(request, f"Đã {state} tài khoản “{target.username}”.")
    logger.info(
        "user_active_toggled",
        extra={"actor_id": request.user.id},
    )
    return redirect("dashboard:user_list")


class RegistrationListView(StaffRequiredMixin, ListView):
    model = Registration
    template_name = "dashboard/registration_list.html"
    context_object_name = "registrations"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            Registration.objects.select_related("user", "event")
            .annotate(ticket_count=Count("tickets"))
            .order_by("-created_at")
        )
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        event_id = self.request.GET.get("event", "").strip()
        if q:
            queryset = queryset.filter(
                Q(user__username__icontains=q)
                | Q(user__email__icontains=q)
                | Q(event__name__icontains=q)
            )
        if status in Registration.Status.values:
            queryset = queryset.filter(status=status)
        if event_id.isdigit():
            queryset = queryset.filter(event_id=event_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "q": self.request.GET.get("q", ""),
                "selected_status": self.request.GET.get("status", ""),
                "selected_event": self.request.GET.get("event", ""),
                "status_choices": Registration.Status.choices,
                "events": Event.objects.order_by("-start_time")[:100],
                "page_title": "Quản lý đăng ký",
                "active_nav": "registrations",
            }
        )
        return context


@staff_required
@require_POST
def cancel_registration_admin(request, pk):
    registration = get_object_or_404(Registration, pk=pk)
    try:
        cancel_registration(
            registration_id=registration.pk,
            actor=request.user,
            by_staff=True,
        )
    except RegistrationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Đã hủy đăng ký và các vé liên quan.")
    return redirect("dashboard:registration_list")


class TicketListView(StaffRequiredMixin, ListView):
    model = Ticket
    template_name = "dashboard/ticket_list.html"
    context_object_name = "tickets"
    paginate_by = 20

    def get_queryset(self):
        queryset = Ticket.objects.select_related(
            "user", "event", "registration"
        ).order_by("-issued_at")
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        event_id = self.request.GET.get("event", "").strip()
        if q:
            query = Q(user__username__icontains=q) | Q(event__name__icontains=q)
            try:
                query |= Q(code=uuid.UUID(q))
            except ValueError:
                pass
            queryset = queryset.filter(query)
        if status in Ticket.Status.values:
            queryset = queryset.filter(status=status)
        if event_id.isdigit():
            queryset = queryset.filter(event_id=event_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "q": self.request.GET.get("q", ""),
                "selected_status": self.request.GET.get("status", ""),
                "selected_event": self.request.GET.get("event", ""),
                "status_choices": Ticket.Status.choices,
                "events": Event.objects.order_by("-start_time")[:100],
                "page_title": "Quản lý vé",
                "active_nav": "tickets_admin",
            }
        )
        return context


@staff_required
@require_POST
def ticket_check_in(request, pk):
    try:
        ticket = check_in_ticket(ticket_id=pk, staff_user=request.user)
    except Ticket.DoesNotExist:
        messages.error(request, "Không tìm thấy vé.")
    except RegistrationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Đã check-in vé {ticket.code_short}.")
    return redirect("dashboard:ticket_list")
