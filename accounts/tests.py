from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class AccountTests(TestCase):
    def test_register_logs_user_in(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "newuser",
                "first_name": "Nguyễn",
                "last_name": "An",
                "email": "an@example.com",
                "phone": "0901234567",
                "password1": "MatKhauRatManh123",
                "password2": "MatKhauRatManh123",
            },
        )
        self.assertRedirects(response, reverse("events:home"))
        user = User.objects.get(username="newuser")
        self.assertEqual(user.email, "an@example.com")
        self.assertTrue(user.is_authenticated)
        response = self.client.get(reverse("events:my_registrations"))
        self.assertEqual(response.status_code, 200)

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(
            username="existing", email="an@example.com", password="Secret12345"
        )
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "newuser",
                "email": "an@example.com",
                "password1": "MatKhauRatManh123",
                "password2": "MatKhauRatManh123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email này đã được sử dụng.")
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_login_and_logout(self):
        user = User.objects.create_user(
            username="alice", password="Secret12345"
        )
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "alice", "password": "Secret12345"},
        )
        self.assertRedirects(response, reverse("events:home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("events:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_login(self):
        User.objects.create_user(
            username="locked", password="Secret12345", is_active=False
        )
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "locked", "password": "Secret12345"},
        )
        self.assertEqual(response.status_code, 200)
        # Không tiết lộ tài khoản có tồn tại hay không: thông báo dùng chung.
        self.assertContains(response, "Tên đăng nhập hoặc mật khẩu không đúng.")
        self.assertNotIn("_auth_user_id", self.client.session)
