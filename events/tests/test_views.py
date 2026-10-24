from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from events.models import Event, Registration, Ticket
from events.services import register_for_event

from .factories import make_event


class EventListViewTests(TestCase):
    def setUp(self):
        self.published = make_event(name="Hội thảo công khai")
        self.draft = make_event(name="Sự kiện nháp", status=Event.Status.DRAFT)
        self.cancelled = make_event(
            name="Sự kiện đã hủy", status=Event.Status.CANCELLED
        )

    def test_only_published_events_are_public(self):
        response = self.client.get(reverse("events:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hội thảo công khai")
        self.assertNotContains(response, "Sự kiện nháp")
        self.assertNotContains(response, "Sự kiện đã hủy")

    def test_search_by_name_and_location(self):
        other = make_event(name="Đêm nhạc", location="Sân vận động")
        response = self.client.get(reverse("events:home"), {"q": "Sân vận động"})
        self.assertContains(response, other.name)
        self.assertNotContains(response, self.published.name)

    def test_filter_by_category(self):
        workshop = make_event(
            name="Workshop Python", category=Event.Category.WORKSHOP
        )
        response = self.client.get(
            reverse("events:home"), {"category": Event.Category.WORKSHOP}
        )
        self.assertContains(response, workshop.name)
        self.assertNotContains(response, self.published.name)

    def test_default_list_hides_past_events(self):
        now = timezone.now()
        past = make_event(
            name="Sự kiện đã qua mặc định",
            start_time=now - timedelta(days=2),
            end_time=now - timedelta(days=1),
            registration_start=now - timedelta(days=10),
            registration_end=now - timedelta(days=3),
        )
        response = self.client.get(reverse("events:home"))
        self.assertContains(response, self.published.name)
        self.assertNotContains(response, past.name)

    def test_filter_past_events(self):
        now = timezone.now()
        past = make_event(
            name="Sự kiện đã qua",
            start_time=now - timedelta(days=2),
            end_time=now - timedelta(days=1),
            registration_start=now - timedelta(days=10),
            registration_end=now - timedelta(days=3),
        )
        response = self.client.get(reverse("events:home"), {"time": "past"})
        self.assertContains(response, past.name)
        self.assertNotContains(response, self.published.name)

    def test_staff_can_preview_draft_detail(self):
        staff = User.objects.create_user(
            username="staff", password="Secret12345", is_staff=True
        )
        url = reverse("events:detail", kwargs={"slug": self.draft.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        self.client.force_login(staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.draft.name)


class RegistrationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="Secret12345")
        self.event = make_event(capacity=5, price=Decimal("50000"))
        self.url = reverse("events:register", kwargs={"slug": self.event.slug})

    def test_login_required(self):
        response = self.client.post(self.url, {"quantity": 1})
        expected = f"{reverse('accounts:login')}?next={self.url}"
        self.assertRedirects(response, expected)

    def test_get_is_not_allowed(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_successful_registration(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"quantity": 2})
        self.assertRedirects(response, reverse("events:my_registrations"))
        registration = Registration.objects.get(user=self.user, event=self.event)
        self.assertEqual(registration.quantity, 2)
        self.assertEqual(registration.tickets.count(), 2)
        self.event.refresh_from_db()
        self.assertEqual(self.event.tickets_sold, 2)

    def test_over_capacity_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"quantity": 6})
        self.assertRedirects(response, self.event.get_absolute_url())
        self.assertFalse(Registration.objects.exists())
        self.event.refresh_from_db()
        self.assertEqual(self.event.tickets_sold, 0)

    def test_duplicate_registration_is_rejected(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"quantity": 1})
        response = self.client.post(self.url, {"quantity": 1}, follow=True)
        self.assertContains(response, "Bạn đã đăng ký sự kiện này rồi.")
        self.assertEqual(Registration.objects.count(), 1)

    def test_my_tickets_page_shows_code_and_status(self):
        registration = register_for_event(
            user=self.user, event_id=self.event.pk, quantity=1
        )
        ticket = registration.tickets.get()
        self.client.force_login(self.user)
        response = self.client.get(reverse("events:my_registrations"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(ticket.code).upper())
        self.assertContains(response, "Hợp lệ")

    def test_cancel_own_registration(self):
        registration = register_for_event(
            user=self.user, event_id=self.event.pk, quantity=2
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("events:cancel_registration", kwargs={"pk": registration.pk})
        )
        self.assertRedirects(response, reverse("events:my_registrations"))
        registration.refresh_from_db()
        self.event.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.CANCELLED)
        self.assertEqual(self.event.tickets_sold, 0)

    def test_cannot_cancel_someone_elses_registration(self):
        registration = register_for_event(
            user=self.user, event_id=self.event.pk, quantity=1
        )
        other = User.objects.create_user(username="bob", password="Secret12345")
        self.client.force_login(other)
        response = self.client.post(
            reverse("events:cancel_registration", kwargs={"pk": registration.pk})
        )
        self.assertEqual(response.status_code, 404)
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.CONFIRMED)

    def test_unauthenticated_detail_asks_for_login(self):
        response = self.client.get(self.event.get_absolute_url())
        self.assertContains(response, "Đăng nhập để đăng ký")
        self.assertNotContains(response, "Đăng ký và nhận vé")
