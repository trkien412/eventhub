import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class EventQuerySet(models.QuerySet):
    def public(self):
        return self.filter(status=Event.Status.PUBLISHED)


class Event(models.Model):
    class Category(models.TextChoices):
        CONFERENCE = "conference", "Hội thảo"
        WORKSHOP = "workshop", "Workshop"
        CONCERT = "concert", "Âm nhạc"
        SPORTS = "sports", "Thể thao"
        OTHER = "other", "Khác"

    class Status(models.TextChoices):
        DRAFT = "draft", "Bản nháp"
        PUBLISHED = "published", "Đang mở"
        CANCELLED = "cancelled", "Đã hủy"

    class RegistrationState(models.TextChoices):
        DRAFT = "draft", "Chưa mở đăng ký"
        NOT_OPEN = "not_open", "Chưa mở đăng ký"
        OPEN = "open", "Đang mở đăng ký"
        CLOSED = "closed", "Đã đóng đăng ký"
        SOLD_OUT = "sold_out", "Hết vé"
        ENDED = "ended", "Đã kết thúc"
        CANCELLED = "cancelled", "Đã hủy"

    name = models.CharField("tên sự kiện", max_length=200)
    slug = models.SlugField("đường dẫn", max_length=220, unique=True, blank=True)
    description = models.TextField("mô tả")
    location = models.CharField("địa điểm", max_length=255)
    category = models.CharField(
        "loại sự kiện",
        max_length=20,
        choices=Category.choices,
        default=Category.CONFERENCE,
        db_index=True,
    )
    start_time = models.DateTimeField("thời gian bắt đầu")
    end_time = models.DateTimeField("thời gian kết thúc")
    registration_start = models.DateTimeField("mở đăng ký")
    registration_end = models.DateTimeField("đóng đăng ký")
    capacity = models.PositiveIntegerField("sức chứa")
    price = models.DecimalField(
        "giá vé (VNĐ)", max_digits=12, decimal_places=0, default=Decimal("0")
    )
    tickets_sold = models.PositiveIntegerField("số vé đã bán", default=0, editable=False)
    status = models.CharField(
        "trạng thái",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_events",
        verbose_name="người tạo",
    )
    created_at = models.DateTimeField("ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("cập nhật lúc", auto_now=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        verbose_name = "sự kiện"
        verbose_name_plural = "sự kiện"
        ordering = ["start_time"]
        indexes = [
            models.Index(fields=["status", "start_time"], name="evt_status_start_idx"),
            models.Index(fields=["category", "start_time"], name="evt_category_start_idx"),
            models.Index(
                fields=["registration_start", "registration_end"],
                name="evt_reg_window_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="event_end_after_start",
            ),
            models.CheckConstraint(
                condition=Q(registration_end__gt=F("registration_start")),
                name="event_reg_window_valid",
            ),
            models.CheckConstraint(
                condition=Q(registration_end__lte=F("start_time")),
                name="event_reg_before_start",
            ),
            models.CheckConstraint(
                condition=Q(capacity__gte=1), name="event_capacity_positive"
            ),
            models.CheckConstraint(
                condition=Q(tickets_sold__gte=0) & Q(tickets_sold__lte=F("capacity")),
                name="event_tickets_within_capacity",
            ),
            models.CheckConstraint(
                condition=Q(price__gte=0), name="event_price_non_negative"
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = {}
        if self.end_time and self.start_time and self.end_time <= self.start_time:
            errors["end_time"] = "Thời gian kết thúc phải sau thời gian bắt đầu."
        if (
            self.registration_start
            and self.registration_end
            and self.registration_end <= self.registration_start
        ):
            errors["registration_end"] = "Thời gian đóng đăng ký phải sau thời gian mở đăng ký."
        if (
            self.registration_end
            and self.start_time
            and self.registration_end > self.start_time
        ):
            errors["registration_end"] = (
                "Đăng ký phải đóng trước hoặc đúng thời điểm sự kiện bắt đầu."
            )
        if self.capacity is not None and self.capacity < 1:
            errors["capacity"] = "Sức chứa phải lớn hơn 0."
        if (
            self.capacity is not None
            and self.tickets_sold is not None
            and self.tickets_sold > self.capacity
        ):
            errors["capacity"] = (
                "Sức chứa không được nhỏ hơn số vé đã bán hiện tại."
            )
        if self.price is not None and self.price < 0:
            errors["price"] = "Giá vé không được âm."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._build_unique_slug()
        super().save(*args, **kwargs)

    def _build_unique_slug(self):
        base = slugify(self.name)[:190] or "su-kien"
        candidate = base
        counter = 2
        while Event.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def get_absolute_url(self):
        return reverse("events:detail", kwargs={"slug": self.slug})

    @property
    def remaining_tickets(self):
        return max(self.capacity - self.tickets_sold, 0)

    @property
    def sold_out(self):
        return self.remaining_tickets == 0

    @property
    def occupancy_percent(self):
        if not self.capacity:
            return 0
        return min(round(self.tickets_sold * 100 / self.capacity), 100)

    @property
    def is_past(self):
        return self.end_time <= timezone.now()

    @property
    def is_ongoing(self):
        now = timezone.now()
        return self.start_time <= now < self.end_time

    def registration_state(self, now=None):
        now = now or timezone.now()
        if self.status == self.Status.DRAFT:
            return self.RegistrationState.DRAFT
        if self.status == self.Status.CANCELLED:
            return self.RegistrationState.CANCELLED
        if now >= self.end_time:
            return self.RegistrationState.ENDED
        if now < self.registration_start:
            return self.RegistrationState.NOT_OPEN
        if now > self.registration_end or now >= self.start_time:
            return self.RegistrationState.CLOSED
        if self.remaining_tickets <= 0:
            return self.RegistrationState.SOLD_OUT
        return self.RegistrationState.OPEN

    @property
    def can_register(self):
        return self.registration_state() == self.RegistrationState.OPEN

    @property
    def registration_state_label(self):
        return self.RegistrationState(self.registration_state()).label

    @property
    def registration_state_message(self):
        state = self.registration_state()
        messages = {
            self.RegistrationState.DRAFT: "Sự kiện chưa được công bố.",
            self.RegistrationState.NOT_OPEN: "Sự kiện chưa mở đăng ký.",
            self.RegistrationState.CLOSED: "Sự kiện đã đóng đăng ký.",
            self.RegistrationState.SOLD_OUT: "Sự kiện đã hết vé.",
            self.RegistrationState.ENDED: "Sự kiện đã kết thúc.",
            self.RegistrationState.CANCELLED: "Sự kiện đã bị hủy.",
        }
        return messages.get(state, "Không thể đăng ký sự kiện này.")

    @property
    def display_price(self):
        if self.price == 0:
            return "Miễn phí"
        return f"{self.price:,.0f} đ".replace(",", ".")


class Registration(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Đã xác nhận"
        CANCELLED = "cancelled", "Đã hủy"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registrations",
        verbose_name="người đăng ký",
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.PROTECT,
        related_name="registrations",
        verbose_name="sự kiện",
    )
    quantity = models.PositiveIntegerField("số lượng vé")
    unit_price = models.DecimalField("đơn giá", max_digits=12, decimal_places=0)
    total_price = models.DecimalField("tổng tiền", max_digits=14, decimal_places=0)
    status = models.CharField(
        "trạng thái",
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
        db_index=True,
    )
    created_at = models.DateTimeField("ngày đăng ký", auto_now_add=True)
    updated_at = models.DateTimeField("cập nhật lúc", auto_now=True)

    class Meta:
        verbose_name = "đăng ký"
        verbose_name_plural = "đăng ký"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event", "status"], name="reg_event_status_idx"),
            models.Index(fields=["user", "status"], name="reg_user_status_idx"),
            models.Index(fields=["created_at"], name="reg_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "event"], name="uniq_registration_user_event"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1), name="registration_quantity_positive"
            ),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.event.name}"

    @property
    def is_cancellable(self):
        return (
            self.status == self.Status.CONFIRMED
            and self.event.start_time > timezone.now()
        )


class Ticket(models.Model):
    class Status(models.TextChoices):
        VALID = "valid", "Hợp lệ"
        USED = "used", "Đã sử dụng"
        CANCELLED = "cancelled", "Đã hủy"

    code = models.UUIDField("mã vé", default=uuid.uuid4, unique=True, editable=False)
    registration = models.ForeignKey(
        Registration,
        on_delete=models.CASCADE,
        related_name="tickets",
        verbose_name="đăng ký",
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="sự kiện",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="người sở hữu",
    )
    status = models.CharField(
        "trạng thái",
        max_length=20,
        choices=Status.choices,
        default=Status.VALID,
        db_index=True,
    )
    issued_at = models.DateTimeField("ngày phát hành", auto_now_add=True)
    checked_in_at = models.DateTimeField("thời gian check-in", null=True, blank=True)

    class Meta:
        verbose_name = "vé"
        verbose_name_plural = "vé"
        ordering = ["issued_at", "id"]
        indexes = [
            models.Index(fields=["event", "status"], name="tkt_event_status_idx"),
            models.Index(fields=["status", "issued_at"], name="tkt_status_issued_idx"),
        ]

    def __str__(self):
        return f"{self.code} - {self.event.name}"

    @property
    def code_display(self):
        return str(self.code).upper()

    @property
    def code_short(self):
        return str(self.code).upper()[:8]
