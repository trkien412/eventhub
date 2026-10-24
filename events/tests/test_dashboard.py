from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from events.models import Event, Registration, Ticket
from events.services import register_for_event

from .factories import make_event


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="Secret12345")
        self.staff = User.objects.create_user(
            username="staff", password="Secret12345", is_staff=True
        )
        self.event = make_event(capacity=10, price=Decimal("50000"), tickets_sold=2)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_normal_user_gets_403(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 403)

    def test_staff_sees_real_statistics(self):
        Registration.objects.create(
            user=self.user,
            event=self.event,
            quantity=2,
            unit_price=self.event.price,
            total_price=Decimal("100000"),
        )
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stats"]["events_total"], 1)
        self.assertEqual(response.context["stats"]["registrations_total"], 1)
        self.assertEqual(response.context["stats"]["tickets_sold"], 2)
        self.assertEqual(response.context["stats"]["revenue"], Decimal("100000"))


class EventManagementTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff", password="Secret12345", is_staff=True
        )
        self.client.force_login(self.staff)

    def _form_data(self, **overrides):
        now = timezone.localtime()
        data = {
            "name": "Sự kiện do quản trị tạo",
            "description": "Mô tả",
            "location": "Hà Nội",
            "category": Event.Category.CONFERENCE,
            "start_time": (now + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M"),
            "end_time": (now + timedelta(days=10, hours=2)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "registration_start": (now - timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "registration_end": (now + timedelta(days=9)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "capacity": 50,
            "price": 0,
            "status": Event.Status.PUBLISHED,
        }
        data.update(overrides)
        return data

    def test_create_event(self):
        response = self.client.post(reverse("dashboard:event_add"), self._form_data())
        self.assertRedirects(response, reverse("dashboard:event_list"))
        event = Event.objects.get(name="Sự kiện do quản trị tạo")
        self.assertEqual(event.created_by, self.staff)
        self.assertEqual(event.slug, "su-kien-do-quan-tri-tao")

    def test_reject_invalid_time_order(self):
        now = timezone.localtime()
        data = self._form_data(
            end_time=(now + timedelta(days=9)).strftime("%Y-%m-%dT%H:%M")
        )
        response = self.client.post(reverse("dashboard:event_add"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thời gian kết thúc phải sau thời gian bắt đầu.")
        self.assertFalse(Event.objects.exists())

    def test_edit_event(self):
        event = make_event()
        data = self._form_data(name="Tên đã đổi")
        response = self.client.post(
            reverse("dashboard:event_edit", kwargs={"pk": event.pk}), data
        )
        self.assertRedirects(response, reverse("dashboard:event_list"))
        event.refresh_from_db()
        self.assertEqual(event.name, "Tên đã đổi")

    def test_cannot_reduce_capacity_below_sold(self):
        event = make_event(capacity=10, tickets_sold=4)
        data = self._form_data(capacity=2)
        response = self.client.post(
            reverse("dashboard:event_edit", kwargs={"pk": event.pk}), data
        )
        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.capacity, 10)

    def test_delete_event_without_registrations(self):
        event = make_event()
        response = self.client.post(
            reverse("dashboard:event_delete", kwargs={"pk": event.pk})
        )
        self.assertRedirects(response, reverse("dashboard:event_list"))
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_delete_event_with_registrations_is_blocked(self):
        event = make_event(capacity=5)
        user = User.objects.create_user(username="alice", password="Secret12345")
        register_for_event(user=user, event_id=event.pk, quantity=1)
        response = self.client.post(
            reverse("dashboard:event_delete", kwargs={"pk": event.pk}), follow=True
        )
        self.assertContains(response, "Không thể xóa sự kiện đã có đăng ký")
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())


class UserManagementTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff", password="Secret12345", is_staff=True
        )
        self.user = User.objects.create_user(
            username="alice", password="Secret12345"
        )
        self.client.force_login(self.staff)

    def test_toggle_user_active(self):
        response = self.client.post(
            reverse("dashboard:user_toggle", kwargs={"pk": self.user.pk})
        )
        self.assertRedirects(response, reverse("dashboard:user_list"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_cannot_lock_self(self):
        response = self.client.post(
            reverse("dashboard:user_toggle", kwargs={"pk": self.staff.pk}),
            follow=True,
        )
        self.assertContains(response, "Bạn không thể tự khóa tài khoản")
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)


class TicketAndRegistrationManagementTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff", password="Secret12345", is_staff=True
        )
        self.user = User.objects.create_user(
            username="alice", password="Secret12345"
        )
        self.event = make_event(capacity=5, price=Decimal("50000"))
        self.registration = register_for_event(
            user=self.user, event_id=self.event.pk, quantity=2
        )
        self.client.force_login(self.staff)

    def test_check_in_ticket(self):
        ticket = self.registration.tickets.first()
        response = self.client.post(
            reverse("dashboard:ticket_check_in", kwargs={"pk": ticket.pk})
        )
        self.assertRedirects(response, reverse("dashboard:ticket_list"))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.USED)
        self.assertIsNotNone(ticket.checked_in_at)

    def test_cancel_registration_from_dashboard(self):
        response = self.client.post(
            reverse(
                "dashboard:registration_cancel",
                kwargs={"pk": self.registration.pk},
            )
        )
        self.assertRedirects(response, reverse("dashboard:registration_list"))
        self.registration.refresh_from_db()
        self.event.refresh_from_db()
        self.assertEqual(self.registration.status, Registration.Status.CANCELLED)
        self.assertEqual(self.event.tickets_sold, 0)

    def test_ticket_filter_by_status(self):
        response = self.client.get(
            reverse("dashboard:ticket_list"), {"status": Ticket.Status.VALID}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["tickets"]), 2)
