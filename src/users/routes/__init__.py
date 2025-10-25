from .profile import router as profile_router
from .admin import router as admin_router
from .moder import router as moder_router
from .public import router as public_router

__all__ = ["profile_router", "admin_router", "moder_router", "public_router"]