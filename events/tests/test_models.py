from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from events.models import Event, Registration, Ticket

from .factories import make_event


class EventModelTests(TestCase):
    def test_slug_is_generated_and_unique(self):
        first = make_event(name="Hội thảo AI")
        second = make_event(name="Hội thảo AI")
        self.assertEqual(first.slug, "hoi-thao-ai")
        self.assertEqual(second.slug, "hoi-thao-ai-2")

    def test_remaining_and_occupancy(self):
        event = make_event(capacity=10, tickets_sold=4)
        self.assertEqual(event.remaining_tickets, 6)
        self.assertEqual(event.occupancy_percent, 40)
        self.assertFalse(event.sold_out)

    def test_registration_states(self):
        now = timezone.now()
        open_event = make_event()
        self.assertEqual(
            open_event.registration_state(now), Event.RegistrationState.OPEN
        )

        draft = make_event(status=Event.Status.DRAFT)
        self.assertEqual(draft.registration_state(now), Event.RegistrationState.DRAFT)

        future = make_event(
            registration_start=now + timedelta(days=1),
            registration_end=now + timedelta(days=2),
            start_time=now + timedelta(days=3),
            end_time=now + timedelta(days=3, hours=2),
        )
        self.assertEqual(
            future.registration_state(now), Event.RegistrationState.NOT_OPEN
        )

        ended = make_event(
            start_time=now - timedelta(days=2),
            end_time=now - timedelta(days=1),
            registration_start=now - timedelta(days=10),
            registration_end=now - timedelta(days=3),
        )
        self.assertEqual(ended.registration_state(now), Event.RegistrationState.ENDED)

        sold_out = make_event(capacity=2, tickets_sold=2)
        self.assertEqual(
            sold_out.registration_state(now), Event.RegistrationState.SOLD_OUT
        )

    def test_clean_rejects_end_before_start(self):
        now = timezone.now()
        event = Event(
            name="Sai thời gian",
            description="x",
            location="x",
            start_time=now + timedelta(days=2),
            end_time=now + timedelta(days=1),
            registration_start=now,
            registration_end=now + timedelta(hours=1),
            capacity=10,
            price=Decimal("0"),
            status=Event.Status.PUBLISHED,
        )
        with self.assertRaises(ValidationError) as ctx:
            event.full_clean()
        self.assertIn("end_time", ctx.exception.message_dict)

    def test_clean_rejects_registration_after_start(self):
        now = timezone.now()
        event = Event(
            name="Sai đăng ký",
            description="x",
            location="x",
            start_time=now + timedelta(days=2),
            end_time=now + timedelta(days=2, hours=1),
            registration_start=now,
            registration_end=now + timedelta(days=3),
            capacity=10,
            price=Decimal("0"),
            status=Event.Status.PUBLISHED,
        )
        with self.assertRaises(ValidationError) as ctx:
            event.full_clean()
        self.assertIn("registration_end", ctx.exception.message_dict)

    def test_clean_rejects_capacity_below_sold(self):
        event = make_event(capacity=5, tickets_sold=3)
        event.capacity = 2
        with self.assertRaises(ValidationError) as ctx:
            event.full_clean()
        self.assertIn("capacity", ctx.exception.message_dict)

    def test_database_check_constraint_blocks_overselling(self):
        event = make_event(capacity=2)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Event.objects.filter(pk=event.pk).update(tickets_sold=3)

    def test_ticket_codes_are_unique(self):
        user = User.objects.create_user(username="u1", password="Secret12345")
        event = make_event()
        registration = Registration.objects.create(
            user=user,
            event=event,
            quantity=2,
            unit_price=event.price,
            total_price=event.price * 2,
        )
        t1 = Ticket.objects.create(registration=registration, event=event, user=user)
        t2 = Ticket.objects.create(registration=registration, event=event, user=user)
        self.assertNotEqual(t1.code, t2.code)
        self.assertEqual(len(str(t1.code)), 36)

    def test_duplicate_registration_is_blocked_by_database(self):
        user = User.objects.create_user(username="u2", password="Secret12345")
        event = make_event()
        payload = {
            "user": user,
            "event": event,
            "quantity": 1,
            "unit_price": event.price,
            "total_price": event.price,
        }
        Registration.objects.create(**payload)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Registration.objects.create(**payload)
