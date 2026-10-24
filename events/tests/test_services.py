from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from accounts.models import User
from events.models import Event, Registration, Ticket
from events.services import (
    RegistrationError,
    cancel_registration,
    check_in_ticket,
    register_for_event,
)

from .factories import make_event


class RegistrationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="Secret12345")
        self.event = make_event(capacity=5, price=Decimal("100000"))

    def test_successful_registration_creates_tickets_and_updates_capacity(self):
        registration = register_for_event(
            user=self.user, event_id=self.event.pk, quantity=2
        )
        self.event.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.CONFIRMED)
        self.assertEqual(registration.quantity, 2)
        self.assertEqual(registration.total_price, Decimal("200000"))
        self.assertEqual(registration.tickets.count(), 2)
        self.assertEqual(self.event.tickets_sold, 2)
        self.assertEqual(self.event.remaining_tickets, 3)
        codes = list(registration.tickets.values_list("code", flat=True))
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(
            all(
                status == Ticket.Status.VALID
                for status in registration.tickets.values_list("status", flat=True)
            )
        )

    def test_duplicate_registration_is_rejected(self):
        register_for_event(user=self.user, event_id=self.event.pk, quantity=1)
        with self.assertRaisesMessage(RegistrationError, "Bạn đã đăng ký"):
            register_for_event(user=self.user, event_id=self.event.pk, quantity=1)
        self.event.refresh_from_db()
        self.assertEqual(self.event.tickets_sold, 1)
        self.assertEqual(Registration.objects.count(), 1)

    def test_cannot_exceed_remaining_tickets(self):
        with self.assertRaisesMessage(RegistrationError, "Chỉ còn 5 vé"):
            register_for_event(user=self.user, event_id=self.event.pk, quantity=6)
        self.event.refresh_from_db()
        self.assertEqual(self.event.tickets_sold, 0)
        self.assertFalse(Registration.objects.exists())

    def test_quantity_must_be_positive(self):
        with self.assertRaisesMessage(RegistrationError, "Số lượng vé"):
            register_for_event(user=self.user, event_id=self.event.pk, quantity=0)
        self.assertFalse(Registration.objects.exists())

    def test_cannot_register_before_open(self):
        now = timezone.now()
        self.event.registration_start = now + timedelta(days=1)
        self.event.registration_end = now + timedelta(days=2)
        self.event.start_time = now + timedelta(days=3)
        self.event.end_time = now + timedelta(days=3, hours=2)
        self.event.save()
        with self.assertRaisesMessage(RegistrationError, "chưa mở đăng ký"):
            register_for_event(user=self.user, event_id=self.event.pk, quantity=1)

    def test_cannot_register_after_event_ended(self):
        now = timezone.now()
        self.event.start_time = now - timedelta(days=2)
        self.event.end_time = now - timedelta(days=1)
        self.event.registration_start = now - timedelta(days=10)
        self.event.registration_end = now - timedelta(days=3)
        self.event.save()
        with self.assertRaisesMessage(RegistrationError, "đã kết thúc"):
            register_for_event(user=self.user, event_id=self.event.pk, quantity=1)

    def test_cannot_register_draft_event(self):
        self.event.status = Event.Status.DRAFT
        self.event.save(update_fields=["status"])
        with self.assertRaisesMessage(RegistrationError, "chưa được công bố"):
            register_for_event(user=self.user, event_id=self.event.pk, quantity=1)

    def test_can_register_exactly_remaining_tickets(self):
        register_for_event(user=self.user, event_id=self.event.pk, quantity=5)
        self.event.refresh_from_db()
        self.assertEqual(self.event.remaining_tickets, 0)

        other = User.objects.create_user(username="bob", password="Secret12345")
        with self.assertRaisesMessage(RegistrationError, "hết vé"):
            register_for_event(user=other, event_id=self.event.pk, quantity=1)

    def test_cancel_restores_capacity_and_cancels_tickets(self):
        registration = register_for_event(
            user=self.user, event_id=self.event.pk, quantity=2
        )
        cancel_registration(
            registration_id=registration.pk, actor=self.user, by_staff=False
        )
        registration.refresh_from_db()
        self.event.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.CANCELLED)
        self.assertEqual(self.event.tickets_sold, 0)
        self.assertEqual(
            registration.tickets.filter(status=Ticket.Status.CANCELLED).count(), 2
        )

        with self.assertRaisesMessage(RegistrationError, "đã được hủy"):
            cancel_registration(
                registration_id=registration.pk, actor=self.user, by_staff=False
            )

    def test_cancel_after_start_is_rejected(self):
        registration = register_for_event(
            user=self.user, event_id=self.event.pk, quantity=1
        )
        now = timezone.now()
        Event.objects.filter(pk=self.event.pk).update(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            registration_start=now - timedelta(days=10),
            registration_end=now - timedelta(hours=2),
        )
        with self.assertRaisesMessage(RegistrationError, "đã bắt đầu"):
            cancel_registration(
                registration_id=registration.pk, actor=self.user, by_staff=False
            )
        self.event.refresh_from_db()
        self.assertEqual(self.event.tickets_sold, 1)

    def test_only_owner_or_staff_can_cancel(self):
        registration = register_for_event(
            user=self.user, event_id=self.event.pk, quantity=1
        )
        other = User.objects.create_user(username="mallory", password="Secret12345")
        with self.assertRaisesMessage(RegistrationError, "không có quyền"):
            cancel_registration(
                registration_id=registration.pk, actor=other, by_staff=False
            )

        # by_staff=True không được tin nếu tài khoản không thực sự là staff.
        with self.assertRaisesMessage(RegistrationError, "không có quyền"):
            cancel_registration(
                registration_id=registration.pk, actor=other, by_staff=True
            )

        staff = User.objects.create_user(
            username="staff", password="Secret12345", is_staff=True
        )
        cancel_registration(registration_id=registration.pk, actor=staff, by_staff=True)
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.CANCELLED)

    def test_check_in_marks_ticket_used(self):
        registration = register_for_event(
            user=self.user, event_id=self.event.pk, quantity=1
        )
        ticket = registration.tickets.get()
        staff = User.objects.create_user(
            username="staff2", password="Secret12345", is_staff=True
        )
        checked = check_in_ticket(ticket_id=ticket.pk, staff_user=staff)
        self.assertEqual(checked.status, Ticket.Status.USED)
        self.assertIsNotNone(checked.checked_in_at)
        with self.assertRaisesMessage(RegistrationError, "đã được check-in"):
            check_in_ticket(ticket_id=ticket.pk, staff_user=staff)

    def test_check_in_rejects_normal_user_and_cancelled_ticket(self):
        registration = register_for_event(
            user=self.user, event_id=self.event.pk, quantity=1
        )
        ticket = registration.tickets.get()
        with self.assertRaisesMessage(RegistrationError, "không có quyền"):
            check_in_ticket(ticket_id=ticket.pk, staff_user=self.user)

        staff = User.objects.create_user(
            username="staff3", password="Secret12345", is_staff=True
        )
        cancel_registration(
            registration_id=registration.pk, actor=self.user, by_staff=False
        )
        with self.assertRaisesMessage(RegistrationError, "đã bị hủy"):
            check_in_ticket(ticket_id=ticket.pk, staff_user=staff)


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentRegistrationTests(TransactionTestCase):
    """Chỉ chạy trên PostgreSQL: kiểm tra khóa dòng chống phát hành quá sức chứa."""

    reset_sequences = True

    def test_concurrent_requests_do_not_oversell(self):
        event = make_event(capacity=5, price=Decimal("0"))
        users = [
            User.objects.create_user(username=f"user{i}", password="Secret12345")
            for i in range(10)
        ]
        barrier = Barrier(len(users))

        def attempt(user):
            close_old_connections()
            barrier.wait()
            try:
                register_for_event(user=user, event_id=event.pk, quantity=1)
                return True
            except RegistrationError:
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(users)) as executor:
            results = list(executor.map(attempt, users))

        event.refresh_from_db()
        self.assertEqual(sum(results), 5)
        self.assertEqual(event.tickets_sold, 5)
        self.assertEqual(Registration.objects.filter(event=event).count(), 5)
        self.assertEqual(Ticket.objects.filter(event=event).count(), 5)
        self.assertEqual(connection.vendor, "postgresql")
