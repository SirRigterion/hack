import ssl
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote_plus

from src.core.config_app import settings
from src.core.config_log import logger


async def send_email(to: str, subject: str, body: str, html: bool = True) -> None:
    """
    Отправка письма через SMTP с SSL (порт 465).
    :param to: Кому отправить
    :param subject: Тема письма
    :param body: Текст письма (строка)
    :param html: True — тело письма будет в HTML, False — обычный текст
    """
    try:
        message = MIMEMultipart()
        message["From"] = settings.SMTP_FROM
        message["To"] = to
        message["Subject"] = subject

        content_type = "html" if html else "plain"
        message.attach(MIMEText(body, content_type, "utf-8"))

        context = ssl.create_default_context()

        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_SERVER,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=True,
            tls_context=context
        )

        logger.info(f"Письмо отправлено на {to}")

    except Exception as e:
        logger.error(f"Ошибка отправки письма на {to}: {e}")
        raise

async def send_verification_email(user_email: str, user_full_name: str, token: str) -> None:
    """Собирает и отправляет письмо для подтверждения почты."""
    verify_link = f"{settings.FRONTEND_URL}/verify-email?token={quote_plus(token)}"

    ttl_seconds = getattr(settings, "VERIFICATION_TTL_SECONDS", 24 * 3600)
    if ttl_seconds >= 3600 and ttl_seconds % 3600 == 0:
        human_ttl = f"{ttl_seconds // 3600} hours"
    else:
        human_ttl = f"{ttl_seconds // 60} minutes"

    subject = "Подтверждение почты"
    html_body = f"""
        <p>Здравствуйте, {user_full_name}!</p>
        <p>Спасибо за регистрацию — чтобы подтвердить адрес электронной почты, перейдите по ссылке:</p>
        <p><a href=\"{verify_link}\">Подтвердить почту</a></p>
        <p>Если ссылка не работает, используйте код ниже на странице подтверждения:</p>
        <pre>{token}</pre>
        <p>Срок действия ссылки: {human_ttl}</p>
        <p>Если вы не регистрировались — проигнорируйте это письмо.</p>
    """
    await send_email(to=user_email, subject=subject, body=html_body, html=True)


async def send_deletion_email(user_email: str, user_full_name: str, token: str, expires_at: str) -> None:
    """Отправляет письмо с возможностью восстановления аккаунта (включая токен)."""
    restore_link = f"{settings.FRONTEND_URL}/restore-account?token={quote_plus(token)}"
    subject = "Восстановление аккаунта"
    html_body = f"""
        <p>Здравствуйте, {user_full_name}!</p>
        <p>Ваш аккаунт был помечен как удалён. Если вы хотите восстановить аккаунт, перейдите по ссылке ниже:</p>
        <p><a href=\"{restore_link}\">Восстановить аккаунт</a></p>
        <p>Срок действия ссылки: {expires_at}</p>
        <p>Если вы не удаляли аккаунт — проигнорируйте это письмо.</p>
    """
    await send_email(to=user_email, subject=subject, body=html_body, html=True)


async def send_reset_password(user_email: str, user_full_name: str, token: str, expires_at: str) -> None:
    """Отправляет письмо с инструкцией по сбросу пароля (включая сырой токен)."""
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={quote_plus(token)}"
    subject = "Сброс пароля"
    html_body = f"""
        <p>Здравствуйте, {user_full_name}!</p>
        <p>Чтобы сбросить пароль, перейдите по ссылке:</p>
        <p><a href="{reset_link}">Сбросить пароль</a></p>
        <p>Если ссылка не работает, используйте код: <pre>{token}</pre></p>
        <p>Срок действия ссылки: {expires_at}</p>
    """
    await send_email(to=user_email, subject=subject, body=html_body, html=True)
