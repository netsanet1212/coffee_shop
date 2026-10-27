import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.db.models import F, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .forms import SignInForm, SignUpForm
from .models import Item, Order, OrderList, Payment


# ---------- Auth ----------

class SignInView(LoginView):
    template_name = "accounts/sign_in.html"
    authentication_form = SignInForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        # "Remember me" unchecked -> session ends when the browser closes.
        if not self.request.POST.get("remember"):
            self.request.session.set_expiry(0)
        return response


class SignOutView(LogoutView):
    pass  # POST only (Django 5+); the header has a small POST form for it


def sign_up(request):
    if request.user.is_authenticated:
        return redirect("item_list")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("item_list")
    return render(request, "accounts/sign_up.html", {"form": form})


# ---------- Chapa (sandbox) ----------

CHAPA_BASE = "https://api.chapa.co/v1"


class ChapaError(Exception):
    pass


def _chapa_headers():
    key = getattr(settings, "CHAPA_SECRET_KEY", "")
    if not key:
        raise ChapaError("Payment is not configured (missing CHAPA_SECRET_KEY).")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _chapa_initialize(request, order_list, payment):
    """Create a Chapa transaction and return its hosted checkout URL."""
    user = request.user
    payload = {
        "amount": f"{payment.amount:.2f}",
        "currency": "ETB",
        "email": user.email or f"{user.get_username()}@example.com",
        "first_name": user.first_name or user.get_username(),
        "last_name": user.last_name or "Customer",
        "tx_ref": payment.reference,
        "return_url": request.build_absolute_uri(
            reverse("payment_return", args=[order_list.pk])
        ),
        "customization": {"title": "Aka Coffee", "description": "Coffee order"},
    }
    try:
        resp = requests.post(
            f"{CHAPA_BASE}/transaction/initialize",
            json=payload, headers=_chapa_headers(), timeout=15,
        )
        body = resp.json()
    except (requests.RequestException, ValueError):
        raise ChapaError("Could not reach the payment service. Please try again.")

    url = (body.get("data") or {}).get("checkout_url")
    if body.get("status") != "success" or not url:
        raise ChapaError("The payment service rejected the request.")
    return url


def _chapa_verify(payment):
    """True if Chapa says this transaction is paid for the right amount.

    Raises ChapaError only when Chapa can't be reached (so we don't cancel a
    possibly-paid order because of a network blip).
    """
    try:
        resp = requests.get(
            f"{CHAPA_BASE}/transaction/verify/{payment.reference}",
            headers=_chapa_headers(), timeout=15,
        )
    except requests.RequestException:
        raise ChapaError("Could not reach the payment service.")
    try:
        body = resp.json()
        data = body.get("data") or {}
        paid = body.get("status") == "success" and data.get("status") == "success"
        return paid and Decimal(str(data.get("amount"))) == payment.amount
    except (ValueError, InvalidOperation, AttributeError):
        return False


def _cancel_order(order_list):
    """Undo an unpaid order: put the stock back and delete it."""
    with transaction.atomic():
        for order in order_list.orders.all():
            Item.objects.filter(pk=order.item_id).update(
                stock_amount=F("stock_amount") + order.quantity
            )
        Payment.objects.filter(order_list=order_list).delete()
        order_list.orders.all().delete()
        order_list.delete()


@login_required
def payment_return(request, pk):
    """Chapa sends the customer back here after checkout."""
    order_list = OrderList.objects.filter(pk=pk, user=request.user).first()
    payment = Payment.objects.filter(order_list=order_list).first() if order_list else None
    if payment is None:
        messages.error(request, "We couldn't find that order.")
        return redirect("item_list")

    try:
        paid = _chapa_verify(payment)
    except ChapaError:
        messages.error(request, "We couldn't confirm your payment yet. Please refresh in a moment.")
        return redirect("track_order")

    if paid:
        messages.success(request, "Payment received. Your order is being prepared.")
        return redirect("track_order")

    _cancel_order(order_list)
    messages.error(request, "Payment was not completed, so the order was cancelled.")
    return redirect("item_list")


@login_required
def item_list(request):
    items = Item.objects.all().order_by("name")

    if request.method == "POST":
        wanted = {}
        for item in items:
            try:
                qty = int(request.POST.get(f"qty_{item.pk}", 0))
            except ValueError:
                qty = 0
            if qty > 0:
                wanted[item.pk] = qty

        if not wanted:
            messages.error(request, "Select at least one item.")
            return redirect("item_list")

        try:
            with transaction.atomic():
                order_list = OrderList.objects.create(user=request.user)
                total = Decimal("0")
                for item in Item.objects.select_for_update().filter(pk__in=wanted):
                    qty = wanted[item.pk]
                    if qty > item.stock_amount:
                        raise ValueError(f"Not enough stock for {item.name}.")
                    item.stock_amount -= qty
                    item.save(update_fields=["stock_amount", "updated_at"])
                    Order.objects.create(order_list=order_list, item=item, quantity=qty)
                    total += item.unit_price * qty
                payment = Payment.objects.create(
                    order_list=order_list,
                    reference=uuid.uuid4().hex[:12].upper(),
                    amount=total,
                )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("item_list")

        try:
            checkout_url = _chapa_initialize(request, order_list, payment)
        except ChapaError as exc:
            _cancel_order(order_list)
            messages.error(request, str(exc))
            return redirect("item_list")

        return redirect(checkout_url)  # Chapa hosted checkout (test mode)

    return render(request, "shop/item_list.html", {"items": items})


def _orders_for(user, status):
    """The user's orders with the given status, newest first (items prefetched)."""
    return (
        OrderList.objects.filter(user=user, order_status=status)
        .prefetch_related("orders__item")
        .order_by("-created_at")
    )


@login_required
def track_order(request):
    """Orders that are still in progress."""
    orders = _orders_for(request.user, OrderList.Status.IN_PROGRESS)
    return render(request, "shop/track_order.html", {"orders": orders})


@login_required
def order_history(request):
    """Orders that are finished."""
    orders = _orders_for(request.user, OrderList.Status.FINISHED)
    return render(request, "shop/order_history.html", {"orders": orders})


# ---------- Admin pages ----------

@staff_member_required(login_url="sign_in")
def stock_management(request):
    if request.method == "POST":
        new_values = {}
        for item in Item.objects.all():
            raw = request.POST.get(f"stock_{item.pk}")
            if raw is None:
                continue
            try:
                value = int(raw)
            except ValueError:
                value = -1
            if value < 0:
                messages.error(request, f"Invalid stock amount for {item.name}.")
                return redirect("stock_management")
            new_values[item.pk] = value

        changed = 0
        with transaction.atomic():
            for item in Item.objects.select_for_update().filter(pk__in=new_values):
                if item.stock_amount != new_values[item.pk]:
                    item.stock_amount = new_values[item.pk]
                    item.save(update_fields=["stock_amount", "updated_at"])
                    changed += 1

        messages.success(request, f"Stock saved ({changed} item{'s' if changed != 1 else ''} changed).")
        return redirect("stock_management")

    items = Item.objects.all().order_by("name")
    return render(request, "shop/stock_management.html", {"items": items})


@staff_member_required(login_url="sign_in")
def order_status_management(request):
    if request.method == "POST":
        try:
            pk = int(request.POST.get("order_id", ""))
        except ValueError:
            pk = None

        updated = 0
        if pk is not None:
            updated = OrderList.objects.filter(
                pk=pk, order_status=OrderList.Status.IN_PROGRESS
            ).update(order_status=OrderList.Status.FINISHED, updated_at=timezone.now())

        if updated:
            messages.success(request, f"Order #{pk} marked as finished.")
        else:
            messages.error(request, "That order could not be updated.")
        return redirect("order_status_management")

    orders = (
        OrderList.objects.select_related("user")
        .prefetch_related("orders__item")
        # "in_progress" sorts after "finished", so descending puts open orders first
        .order_by("-order_status", "-created_at")
    )
    return render(request, "shop/order_status.html", {"orders": orders})


# ---------- Audit report ----------

def _period_start(key):
    """Start of the current day / week (Monday) / month / year, in local time."""
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    if key == "week":
        start -= timedelta(days=start.weekday())
    elif key == "month":
        start = start.replace(day=1)
    elif key == "year":
        start = start.replace(month=1, day=1)
    return start


def _audit_stats(key):
    start = _period_start(key)
    orders = OrderList.objects.filter(created_at__gte=start)
    revenue = (
        Payment.objects.filter(created_at__gte=start).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )
    return {
        "orders": orders.count(),
        "users": orders.values("user").distinct().count(),  # customers who ordered
        "revenue": revenue,  # ETB
    }


@staff_member_required(login_url="sign_in")
def audit_report(request):
    return render(request, "shop/audit_report.html", {"stats": _audit_stats("today")})


@staff_member_required(login_url="sign_in")
@require_GET
def audit_stats(request):
    """JSON used by the filter buttons: ?range=today|week|month|year"""
    stats = _audit_stats(request.GET.get("range", "today"))
    stats["revenue"] = str(stats["revenue"])
    return JsonResponse(stats)