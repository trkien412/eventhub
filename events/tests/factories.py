from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from events.models import Event


def make_event(**overrides):
    now = timezone.now()
    defaults = {
        "name": "Sự kiện kiểm thử",
        "description": "Mô tả sự kiện kiểm thử.",
        "location": "Hội trường kiểm thử",
        "category": Event.Category.CONFERENCE,
        "start_time": now + timedelta(days=5),
        "end_time": now + timedelta(days=5, hours=2),
        "registration_start": now - timedelta(days=1),
        "registration_end": now + timedelta(days=4),
        "capacity": 10,
        "price": Decimal("100000"),
        "status": Event.Status.PUBLISHED,
    }
    defaults.update(overrides)
    return Event.objects.create(**defaults)
