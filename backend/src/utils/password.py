import secrets
import bcrypt


def generate_salt(nbytes: int = 16) -> str:
    """Генерирует криптографически стойкую соль."""
    return secrets.token_hex(nbytes)

def hash_password_with_pepper(password: str, pepper: str) -> str:
    """
    Хеширует пароль с использованием bcrypt и pepper.
    Pepper добавляется к паролю перед хешированием bcrypt.
    """
    password_with_pepper = password + pepper
    return bcrypt.hashpw(password_with_pepper.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password_with_pepper(plain_password: str, hashed_password: str, pepper: str) -> bool:
    """
    Проверяет соответствие пароля хешу с учетом pepper.
    """
    password_with_pepper = plain_password + pepper
    return bcrypt.checkpw(password_with_pepper.encode('utf-8'), hashed_password.encode('utf-8'))

def hash_password(password: str) -> str:
    """
    ! НЕ Используеться ни где !
    Хеширует пароль с использованием bcrypt (без pepper).
    """
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    ! НЕ Используеться ни где !
    Проверяет соответствие пароля хешу (без pepper).
    """
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))