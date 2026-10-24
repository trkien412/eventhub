"""Tạo dữ liệu sự kiện mẫu (không tạo tài khoản/mật khẩu).

Chạy: python manage.py seed_events
Lệnh có tính idempotent: chỉ tạo sự kiện chưa tồn tại theo slug.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from events.models import Event


class Command(BaseCommand):
    help = "Tao mot so su kien mau de thu giao dien va chuc nang."

    def handle(self, *args, **options):
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        def at(day_offset, hour, minute=0):
            return (now + timedelta(days=day_offset)).replace(
                hour=hour, minute=minute
            )

        samples = [
            {
                "slug": "hoi-thao-ai-du-lieu-2026",
                "name": "Hội thảo AI & Dữ liệu 2026",
                "description": (
                    "Hội thảo dành cho sinh viên và kỹ sư yêu thích trí tuệ nhân tạo. "
                    "Các diễn giả chia sẻ về ứng dụng AI trong doanh nghiệp, kỹ năng "
                    "xây dựng sản phẩm dữ liệu và định hướng nghề nghiệp."
                ),
                "location": "Hội trường A, Đại học Công nghệ",
                "category": Event.Category.CONFERENCE,
                "start_time": at(14, 9),
                "end_time": at(14, 12),
                "registration_start": now - timedelta(days=7),
                "registration_end": at(13, 9),
                "capacity": 150,
                "price": Decimal("150000"),
                "status": Event.Status.PUBLISHED,
            },
            {
                "slug": "workshop-django-tu-a-den-z",
                "name": "Workshop Django từ A đến Z",
                "description": (
                    "Thực hành xây dựng một website hoàn chỉnh với Django: model, "
                    "view, template, xác thực người dùng và triển khai bằng Docker. "
                    "Hãy mang theo laptop cá nhân."
                ),
                "location": "Phòng thực hành 302, Tòa nhà B",
                "category": Event.Category.WORKSHOP,
                "start_time": at(21, 13, 30),
                "end_time": at(21, 17),
                "registration_start": now - timedelta(days=3),
                "registration_end": at(20, 13, 30),
                "capacity": 40,
                "price": Decimal("50000"),
                "status": Event.Status.PUBLISHED,
            },
            {
                "slug": "dem-nhac-sinh-vien-2026",
                "name": "Đêm nhạc Sinh viên 2026",
                "description": (
                    "Một đêm nhạc ngoài trời với sự tham gia của các câu lạc bộ âm nhạc "
                    "trong trường. Không gian check-in, food truck và giao lưu nghệ sĩ."
                ),
                "location": "Sân vận động Đại học",
                "category": Event.Category.CONCERT,
                "start_time": at(30, 19),
                "end_time": at(30, 22),
                "registration_start": now,
                "registration_end": at(29, 19),
                "capacity": 300,
                "price": Decimal("120000"),
                "status": Event.Status.PUBLISHED,
            },
            {
                "slug": "giai-chay-vi-cong-dong",
                "name": "Giải chạy vì cộng đồng",
                "description": (
                    "Giải chạy phong trào 5km và 10km nhằm gây quỹ cho quỹ học bổng "
                    "sinh viên. Mỗi người tham gia nhận áo, huy chương và nước uống."
                ),
                "location": "Công viên trung tâm thành phố",
                "category": Event.Category.SPORTS,
                "start_time": at(45, 6),
                "end_time": at(45, 10),
                "registration_start": now - timedelta(days=2),
                "registration_end": at(44, 6),
                "capacity": 500,
                "price": Decimal("0"),
                "status": Event.Status.PUBLISHED,
            },
            {
                "slug": "talkshow-ky-nang-nghe-nghiep",
                "name": "Talkshow Kỹ năng nghề nghiệp",
                "description": (
                    "Chuỗi chia sẻ về kỹ năng viết CV, phỏng vấn và thích nghi với "
                    "môi trường làm việc đầu tiên. Sự kiện đã kết thúc."
                ),
                "location": "Hội trường C",
                "category": Event.Category.CONFERENCE,
                "start_time": at(-10, 9),
                "end_time": at(-10, 11),
                "registration_start": at(-25, 9),
                "registration_end": at(-11, 9),
                "capacity": 100,
                "price": Decimal("0"),
                "status": Event.Status.PUBLISHED,
            },
            {
                "slug": "su-kien-dang-chuan-bi",
                "name": "Sự kiện đang chuẩn bị (bản nháp)",
                "description": (
                    "Sự kiện nháp dùng để kiểm tra quyền quản trị. Người dùng thường "
                    "không nhìn thấy sự kiện này."
                ),
                "location": "Đang cập nhật",
                "category": Event.Category.OTHER,
                "start_time": at(60, 9),
                "end_time": at(60, 12),
                "registration_start": at(30, 9),
                "registration_end": at(59, 9),
                "capacity": 80,
                "price": Decimal("0"),
                "status": Event.Status.DRAFT,
            },
        ]

        created = 0
        for data in samples:
            _, was_created = Event.objects.get_or_create(slug=data["slug"], defaults=data)
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"[OK] Da tao: {data['slug']}"))
            else:
                self.stdout.write(f"[SKIP] Da ton tai: {data['slug']}")

        self.stdout.write(
            self.style.SUCCESS(f"Hoan tat. Da them {created} su kien mau.")
        )
