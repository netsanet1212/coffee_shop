# models.py
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.email

class Item(TimeStampedModel):
    name = models.CharField(max_length=100)
    stock_amount = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="items/", blank=True, null=True)

    def __str__(self):   
        return self.name


class OrderList(TimeStampedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        FINISHED = "finished", "Finished"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="order_lists"
    )
    order_status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IN_PROGRESS
    )

    @property
    def total(self):
        """Sum of all lines. Use prefetch_related("orders__item") to avoid extra queries."""
        return sum((line.subtotal for line in self.orders.all()), Decimal("0"))


class Order(TimeStampedModel):
    order_list = models.ForeignKey(
        OrderList, on_delete=models.CASCADE, related_name="orders"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)

    @property
    def subtotal(self):
        return self.item.unit_price * self.quantity


class Payment(TimeStampedModel):
    order_list = models.ForeignKey(
        OrderList, on_delete=models.PROTECT, related_name="payments"
    )
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)