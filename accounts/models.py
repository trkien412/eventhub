from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse


class User(AbstractUser):
    """Người dùng hệ thống.

    Tài khoản quản trị được phân biệt bằng is_staff = True. Không tạo thêm
    bảng Role riêng để giữ dự án đơn giản, phù hợp đồ án sinh viên.
    """

    phone = models.CharField("số điện thoại", max_length=20, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "người dùng"
        verbose_name_plural = "người dùng"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.username

    @property
    def display_name(self):
        return self.get_full_name().strip() or self.username

    @property
    def is_event_admin(self):
        return self.is_active and self.is_staff

    def get_absolute_url(self):
        return reverse("events:home")
