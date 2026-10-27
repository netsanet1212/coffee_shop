from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Item, Order, OrderList, Payment, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "phone", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "unit_price", "stock_amount", "updated_at")
    list_editable = ("unit_price", "stock_amount")   # edit stock inline from the list
    search_fields = ("name",)


class OrderInline(admin.TabularInline):
    model = Order
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(OrderList)
class OrderListAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "order_status", "created_at")
    list_editable = ("order_status",)                # change status inline from the list
    list_filter = ("order_status",)
    inlines = [OrderInline, PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "order_list", "amount", "created_at")