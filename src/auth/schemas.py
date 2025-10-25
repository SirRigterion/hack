from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class UserCreate(BaseModel):
    user_login: str = Field(min_length=3, max_length=50)
    user_full_name: str = Field(min_length=2, max_length=100)
    user_email: EmailStr = Field(min_length=3, max_length=100)
    user_password: str = Field(min_length=8, max_length=128)

    @field_validator("user_login")
    def validate_login(cls, value: str) -> str:
        if not re.match(r'^[a-zA-Z0-9_]+$', value):
            raise ValueError("Имя пользователя может содержать только английские буквы, цифры и подчеркивание")
        return value

    @field_validator("user_full_name")
    def validate_full_name(cls, value: str) -> str:
        if not re.match(r'^[a-zA-Zа-яА-ЯёЁ\s\-]+$', value):
            raise ValueError("Полное имя может содержать только русские или английские буквы, пробелы и дефис")
        return value

    @field_validator("user_password")
    def validate_password(cls, value: str) -> str:
        if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*])[A-Za-z\d!@#$%^&*]{8,}$', value):
            raise ValueError("Пароль должен содержать минимум 8 символов, включая хотя бы одну заглавную букву, одну строчную букву, одну цифру и один специальный символ (!@#$%^&*)")
        return value
    
class UserLogin(BaseModel):
    user_indificator: str = Field(min_length=3, max_length=50)
    user_password: str = Field(min_length=8, max_length=255)
