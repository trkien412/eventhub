"""Nghiệp vụ đăng ký sự kiện và vé.

Mọi thao tác thay đổi số vé đều chạy trong transaction và khóa dòng sự kiện
(select_for_update) để tránh bán vượt sức chứa khi có nhiều request đồng thời.
"""
import logging
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Event, Registration, Ticket

logger = logging.getLogger("events")


class RegistrationError(Exception):
    """Lỗi nghiệp vụ có thông điệp hiển thị được cho người dùng."""


def register_for_event(*, user, event_id: int, quantity: int) -> Registration:
    if quantity < 1:
        raise RegistrationError("Số lượng vé phải từ 1 trở lên.")

    try:
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=event_id)
            now = timezone.now()

            if event.registration_state(now) != Event.RegistrationState.OPEN:
                raise RegistrationError(event.registration_state_message)

            if quantity > event.remaining_tickets:
                raise RegistrationError(
                    f"Chỉ còn {event.remaining_tickets} vé. Vui lòng chọn số lượng nhỏ hơn."
                )

            if Registration.objects.filter(user=user, event=event).exists():
                raise RegistrationError("Bạn đã đăng ký sự kiện này rồi.")

            registration = Registration.objects.create(
                user=user,
                event=event,
                quantity=quantity,
                unit_price=event.price,
                total_price=event.price * quantity,
                status=Registration.Status.CONFIRMED,
            )

            # Đang giữ khóa trên dòng Event nên phép cộng này an toàn.
            event.tickets_sold += quantity
            event.save(update_fields=["tickets_sold", "updated_at"])

            Ticket.objects.bulk_create(
                [
                    Ticket(
                        code=uuid.uuid4(),
                        registration=registration,
                        event=event,
                        user=user,
                        status=Ticket.Status.VALID,
                    )
                    for _ in range(quantity)
                ]
            )
    except Event.DoesNotExist as exc:
        raise RegistrationError("Sự kiện không tồn tại.") from exc
    except IntegrityError as exc:
        # Ràng buộc unique/check của database là lớp bảo vệ cuối cùng.
        logger.warning(
            "ticket_registration_rejected",
            extra={"event_id": event_id, "actor_id": user.id},
        )
        raise RegistrationError(
            "Không thể hoàn tất đăng ký do dữ liệu vừa thay đổi. Vui lòng thử lại."
        ) from exc

    logger.info(
        "ticket_registration_created",
        extra={
            "event_id": event.id,
            "registration_id": registration.id,
            "actor_id": user.id,
            "quantity": quantity,
        },
    )
    return registration


def cancel_registration(*, registration_id: int, actor, by_staff: bool = False):
    # by_staff chỉ có hiệu lực khi actor thực sự là staff; không tin tham số
    # do nơi gọi truyền vào.
    if by_staff and not actor.is_staff:
        raise RegistrationError("Bạn không có quyền hủy đăng ký của người khác.")

    with transaction.atomic():
        registration = (
            Registration.objects.select_for_update()
            .select_related("event")
            .get(pk=registration_id)
        )
        if not by_staff and registration.user_id != actor.id:
            raise RegistrationError("Bạn không có quyền hủy đăng ký này.")
        if registration.status == Registration.Status.CANCELLED:
            raise RegistrationError("Đăng ký này đã được hủy trước đó.")

        event = Event.objects.select_for_update().get(pk=registration.event_id)
        if event.start_time <= timezone.now():
            raise RegistrationError(
                "Không thể hủy đăng ký sau khi sự kiện đã bắt đầu."
            )

        registration.status = Registration.Status.CANCELLED
        registration.save(update_fields=["status", "updated_at"])
        registration.tickets.filter(status=Ticket.Status.VALID).update(
            status=Ticket.Status.CANCELLED
        )
        event.tickets_sold = max(event.tickets_sold - registration.quantity, 0)
        event.save(update_fields=["tickets_sold", "updated_at"])

    logger.info(
        "ticket_registration_cancelled",
        extra={
            "event_id": event.id,
            "registration_id": registration.id,
            "actor_id": actor.id,
            "quantity": registration.quantity,
        },
    )
    return registration


def check_in_ticket(*, ticket_id: int, staff_user) -> Ticket:
    if not staff_user.is_staff:
        raise RegistrationError("Bạn không có quyền check-in vé.")

    with transaction.atomic():
        ticket = (
            Ticket.objects.select_for_update()
            .select_related("event")
            .get(pk=ticket_id)
        )
        if ticket.status == Ticket.Status.CANCELLED:
            raise RegistrationError("Vé đã bị hủy, không thể check-in.")
        if ticket.status == Ticket.Status.USED:
            raise RegistrationError("Vé này đã được check-in trước đó.")
        if ticket.event.status == Event.Status.CANCELLED:
            raise RegistrationError("Sự kiện đã bị hủy.")

        ticket.status = Ticket.Status.USED
        ticket.checked_in_at = timezone.now()
        ticket.save(update_fields=["status", "checked_in_at"])

    logger.info(
        "ticket_checked_in",
        extra={"event_id": ticket.event_id, "ticket_id": ticket.id, "actor_id": staff_user.id},
    )
    return ticket
