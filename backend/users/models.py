from django.db import models

# Create your models here.
import uuid
from django.contrib.auth.models import AbstractUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from django.utils.translation import gettext_lazy as _
from django.conf import settings
from .managers import CustomUserManager


import secrets
from datetime import timedelta


class CustomUser(AbstractUser):
    email = models.EmailField(_("email address"), unique=True)
    name = models.CharField(max_length=100, null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager() #type: ignore

    def __str__(self):
        return self.email

    class Meta:
        db_table = "custom_user"
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [
            models.UniqueConstraint(fields=['email'], name='unique_email_constraint')
        ]


class PasswordResetToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_reset_tokens',
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = 'password_reset_token'

    def __str__(self):
        return f"PasswordResetToken({self.user.email}, used={self.is_used})"

    @classmethod
    def create_for_user(cls, user):
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(hours=1)
        return cls.objects.create(user=user, token=token, expires_at=expires_at)

    @property
    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()