from django import forms
from django.utils import timezone

from .models import Event


class EventFilterForm(forms.Form):
    TIME_CHOICES = [
        ("upcoming", "Sắp diễn ra"),
        ("past", "Đã kết thúc"),
        ("all", "Tất cả thời gian"),
    ]

    q = forms.CharField(
        label="Tìm kiếm",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Tên sự kiện, địa điểm...",
                "aria-label": "Tìm kiếm sự kiện",
            }
        ),
    )
    category = forms.ChoiceField(
        label="Loại sự kiện",
        required=False,
        choices=[("", "Tất cả loại")] + list(Event.Category.choices),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    date = forms.DateField(
        label="Ngày tổ chức",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    time = forms.ChoiceField(
        label="Thời gian",
        required=False,
        choices=TIME_CHOICES,
        initial="upcoming",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def clean_time(self):
        return self.cleaned_data.get("time") or "upcoming"


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = (
            "name",
            "description",
            "location",
            "category",
            "start_time",
            "end_time",
            "registration_start",
            "registration_end",
            "capacity",
            "price",
            "status",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Tên sự kiện"}
            ),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 5, "placeholder": "Mô tả sự kiện"}
            ),
            "location": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Địa điểm tổ chức"}
            ),
            "category": forms.Select(attrs={"class": "form-control"}),
            "start_time": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "end_time": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "registration_start": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "registration_end": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "capacity": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "placeholder": "Số chỗ"}
            ),
            "price": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "step": 1000}
            ),
            "status": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        date_fields = (
            "start_time",
            "end_time",
            "registration_start",
            "registration_end",
        )
        for field_name in date_fields:
            self.fields[field_name].input_formats = [
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
            ]
        self.fields["description"].help_text = (
            "Thông tin chi tiết về chương trình, diễn giả, lưu ý khi tham dự."
        )
        self.fields["price"].help_text = "Nhập 0 nếu sự kiện miễn phí."
        self.fields["capacity"].help_text = "Tổng số vé tối đa có thể phát hành."

    # Quy tắc thời gian/sức chứa/giá nằm duy nhất trong Event.clean(); ModelForm
    # tự gọi full_clean() và gắn lỗi vào đúng trường nên không lặp lại ở đây.


class RegistrationForm(forms.Form):
    quantity = forms.IntegerField(
        label="Số lượng vé",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(
            attrs={"class": "form-control ticket-quantity", "min": 1, "step": 1}
        ),
    )

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        if event:
            remaining = max(event.remaining_tickets, 1)
            self.fields["quantity"].widget.attrs["max"] = remaining
            self.fields["quantity"].help_text = (
                f"Còn {event.remaining_tickets} vé. Mỗi tài khoản đăng ký một lần."
            )

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if self.event and quantity > self.event.remaining_tickets:
            raise forms.ValidationError(
                f"Chỉ còn {self.event.remaining_tickets} vé cho sự kiện này."
            )
        return quantity
