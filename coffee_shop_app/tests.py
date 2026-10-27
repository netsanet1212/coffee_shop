"""
Tests for coffeshopapp.

Run with:  python manage.py test coffeshopapp

Chapa is always mocked (requests.post / requests.get), so no network or real
API key is needed.
"""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import requests
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import views
from .forms import SignInForm, SignUpForm
from .models import Item, Order, OrderList, Payment

User = get_user_model()

PASSWORD = "Str0ng-pass-93!"
CHECKOUT_URL = "https://checkout.chapa.co/checkout/payment/abc123"


# ---------------------------------------------------------------- helpers

def make_user(email="customer@example.com", **extra):
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


def make_staff(email="staff@example.com"):
    return make_user(email, is_staff=True)


def make_item(name="Latte", price="50.00", stock=10):
    return Item.objects.create(name=name, unit_price=Decimal(price), stock_amount=stock)


def make_order(user, lines, reference="REF000000001", status=None):
    """Create an order the way item_list does: stock deducted + Payment row.

    lines: list of (item, quantity)
    """
    order_list = OrderList.objects.create(user=user)
    if status:
        order_list.order_status = status
        order_list.save()
    total = Decimal("0")
    for item, qty in lines:
        item.stock_amount -= qty
        item.save()
        Order.objects.create(order_list=order_list, item=item, quantity=qty)
        total += item.unit_price * qty
    payment = Payment.objects.create(order_list=order_list, reference=reference, amount=total)
    return order_list, payment


def messages_of(response):
    return [(m.level_tag, str(m)) for m in get_messages(response.wsgi_request)]


def chapa_init_ok(url=CHECKOUT_URL):
    resp = mock.Mock()
    resp.json.return_value = {
        "status": "success",
        "message": "Hosted Link",
        "data": {"checkout_url": url},
    }
    return resp


def chapa_verify_response(status="success", amount="100.00", outer="success"):
    resp = mock.Mock()
    resp.json.return_value = {
        "status": outer,
        "data": {"status": status, "amount": amount},
    }
    return resp


# ----------------------------------------------------------------- models

class UserModelTests(TestCase):
    def test_create_user_uses_email_and_hashes_password(self):
        user = make_user("Someone@EXAMPLE.com")
        self.assertEqual(user.email, "Someone@example.com")  # domain lower-cased
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.is_staff)
        self.assertEqual(str(user), user.email)

    def test_create_user_requires_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password=PASSWORD)

    def test_create_superuser_sets_flags(self):
        admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)


class OrderModelTests(TestCase):
    def test_subtotal_and_total(self):
        user = make_user()
        latte = make_item("Latte", "50.00")
        tea = make_item("Tea", "20.50")
        order_list, _ = make_order(user, [(latte, 2), (tea, 3)])

        self.assertEqual(order_list.orders.get(item=latte).subtotal, Decimal("100.00"))
        self.assertEqual(order_list.total, Decimal("161.50"))

    def test_total_of_empty_order_list_is_zero(self):
        order_list = OrderList.objects.create(user=make_user())
        self.assertEqual(order_list.total, Decimal("0"))

    def test_new_order_list_defaults_to_in_progress(self):
        order_list = OrderList.objects.create(user=make_user())
        self.assertEqual(order_list.order_status, OrderList.Status.IN_PROGRESS)

    def test_item_str(self):
        self.assertEqual(str(make_item("Macchiato")), "Macchiato")


# ------------------------------------------------------------------ forms

class SignUpFormTests(TestCase):
    def data(self, **overrides):
        data = {
            "first_name": "Abebe",
            "last_name": "Kebede",
            "email": "abebe@example.com",
            "phone": "+251 911-234-567",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(overrides)
        return data

    def test_valid_form_normalises_phone_to_digits(self):
        form = SignUpForm(self.data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "251911234567")

    def test_invalid_phone_rejected(self):
        form = SignUpForm(self.data(phone="12ab"))
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_too_short_phone_rejected(self):
        form = SignUpForm(self.data(phone="12345"))
        self.assertFalse(form.is_valid())

    def test_names_and_phone_are_required(self):
        form = SignUpForm(self.data(first_name="", last_name="", phone=""))
        self.assertFalse(form.is_valid())
        for field in ("first_name", "last_name", "phone"):
            self.assertIn(field, form.errors)

    def test_password_mismatch(self):
        form = SignUpForm(self.data(password2="different-pass-1!"))
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_duplicate_email_rejected(self):
        make_user("abebe@example.com")
        form = SignUpForm(self.data())
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class SignInFormTests(TestCase):
    def test_username_field_is_an_email_field(self):
        form = SignInForm(data={"username": "not-an-email", "password": "x"})
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)


# ------------------------------------------------------------------- auth

class AuthViewTests(TestCase):
    def test_sign_up_creates_user_and_logs_in(self):
        response = self.client.post(reverse("sign_up"), {
            "first_name": "Abebe",
            "last_name": "Kebede",
            "email": "abebe@example.com",
            "phone": "0911234567",
            "password1": PASSWORD,
            "password2": PASSWORD,
        })
        self.assertRedirects(response, reverse("item_list"), fetch_redirect_response=False)
        user = User.objects.get(email="abebe@example.com")
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_sign_up_with_invalid_data_shows_form_again(self):
        response = self.client.post(reverse("sign_up"), {"email": "bad"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())
        self.assertEqual(User.objects.count(), 0)

    def test_sign_up_redirects_authenticated_user(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse("sign_up"))
        self.assertRedirects(response, reverse("item_list"), fetch_redirect_response=False)

    def test_sign_in_page_loads(self):
        self.assertEqual(self.client.get(reverse("sign_in")).status_code, 200)

    def test_sign_in_with_wrong_password_fails(self):
        make_user("a@example.com")
        response = self.client.post(reverse("sign_in"), {"username": "a@example.com", "password": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Incorrect email or password.", response.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sign_in_without_remember_expires_at_browser_close(self):
        make_user("a@example.com")
        self.client.post(reverse("sign_in"), {"username": "a@example.com", "password": PASSWORD})
        self.assertIn("_auth_user_id", self.client.session)
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_sign_in_with_remember_keeps_session(self):
        make_user("a@example.com")
        self.client.post(reverse("sign_in"), {
            "username": "a@example.com", "password": PASSWORD, "remember": "on",
        })
        self.assertIn("_auth_user_id", self.client.session)
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_sign_out_logs_user_out(self):
        self.client.force_login(make_user())
        self.client.post(reverse("sign_out"))
        self.assertNotIn("_auth_user_id", self.client.session)


# -------------------------------------------------- login protection / pages

class LoginRequiredTests(TestCase):
    def test_customer_pages_redirect_anonymous_users(self):
        for name in ("item_list", "track_order", "order_history"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("sign-in", response["Location"])

    def test_payment_return_requires_login(self):
        response = self.client.get(reverse("payment_return", args=[1]))
        self.assertEqual(response.status_code, 302)

    def test_staff_pages_redirect_anonymous_and_regular_users(self):
        names = ("stock_management", "order_status_management", "audit_report", "audit_stats")
        for name in names:
            with self.subTest(name=name, who="anonymous"):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
        self.client.force_login(make_user())
        for name in names:
            with self.subTest(name=name, who="customer"):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("sign-in", response["Location"])


# --------------------------------------------------------- menu / checkout

@override_settings(CHAPA_SECRET_KEY="CHASECK_TEST-abc")
class ItemListTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.latte = make_item("Latte", "50.00", stock=10)
        self.tea = make_item("Tea", "20.00", stock=5)

        patcher = mock.patch("coffeshopapp.views.requests.post")
        self.post = patcher.start()
        self.addCleanup(patcher.stop)
        self.post.return_value = chapa_init_ok()

    def checkout(self, **qty):
        """qty keys are item attribute names, e.g. checkout(latte=2)."""
        data = {f"qty_{getattr(self, name).pk}": str(n) for name, n in qty.items()}
        return self.client.post(reverse("item_list"), data)

    # -- GET
    def test_menu_lists_items_alphabetically(self):
        make_item("Americano")
        response = self.client.get(reverse("item_list"))
        self.assertEqual(response.status_code, 200)
        names = [i.name for i in response.context["items"]]
        self.assertEqual(names, ["Americano", "Latte", "Tea"])

    # -- validation
    def test_empty_order_is_rejected(self):
        response = self.client.post(reverse("item_list"), {})
        self.assertRedirects(response, reverse("item_list"), fetch_redirect_response=False)
        self.assertIn(("error", "Select at least one item."), messages_of(response))
        self.assertEqual(OrderList.objects.count(), 0)
        self.post.assert_not_called()

    def test_zero_negative_and_non_numeric_quantities_are_ignored(self):
        response = self.client.post(reverse("item_list"), {
            f"qty_{self.latte.pk}": "0",
            f"qty_{self.tea.pk}": "abc",
        })
        self.assertIn(("error", "Select at least one item."), messages_of(response))
        response = self.client.post(reverse("item_list"), {f"qty_{self.latte.pk}": "-4"})
        self.assertIn(("error", "Select at least one item."), messages_of(response))
        self.assertEqual(OrderList.objects.count(), 0)

    def test_bad_quantity_for_one_item_does_not_block_the_others(self):
        response = self.client.post(reverse("item_list"), {
            f"qty_{self.latte.pk}": "abc",
            f"qty_{self.tea.pk}": "1",
        })
        self.assertRedirects(response, CHECKOUT_URL, fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().item, self.tea)

    def test_not_enough_stock_creates_nothing(self):
        response = self.checkout(latte=11)
        self.assertRedirects(response, reverse("item_list"), fetch_redirect_response=False)
        self.assertIn(("error", "Not enough stock for Latte."), messages_of(response))
        self.assertEqual(OrderList.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.latte.refresh_from_db()
        self.assertEqual(self.latte.stock_amount, 10)
        self.post.assert_not_called()

    def test_one_item_over_stock_rolls_back_the_others(self):
        self.checkout(latte=2, tea=99)
        self.assertEqual(OrderList.objects.count(), 0)
        self.latte.refresh_from_db()
        self.assertEqual(self.latte.stock_amount, 10)

    # -- happy path
    def test_successful_checkout_creates_order_payment_and_redirects_to_chapa(self):
        response = self.checkout(latte=2, tea=1)
        self.assertRedirects(response, CHECKOUT_URL, fetch_redirect_response=False)

        order_list = OrderList.objects.get()
        self.assertEqual(order_list.user, self.user)
        self.assertEqual(order_list.order_status, OrderList.Status.IN_PROGRESS)
        self.assertEqual(order_list.orders.count(), 2)

        payment = Payment.objects.get()
        self.assertEqual(payment.order_list, order_list)
        self.assertEqual(payment.amount, Decimal("120.00"))
        self.assertEqual(len(payment.reference), 12)
        self.assertEqual(payment.reference, payment.reference.upper())

        self.latte.refresh_from_db()
        self.tea.refresh_from_db()
        self.assertEqual(self.latte.stock_amount, 8)
        self.assertEqual(self.tea.stock_amount, 4)

    def test_chapa_is_called_with_the_right_payload(self):
        self.checkout(latte=2)
        payment = Payment.objects.get()

        self.assertEqual(self.post.call_count, 1)
        args, kwargs = self.post.call_args
        self.assertEqual(args[0], "https://api.chapa.co/v1/transaction/initialize")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer CHASECK_TEST-abc")

        body = kwargs["json"]
        self.assertEqual(body["amount"], "100.00")
        self.assertEqual(body["currency"], "ETB")
        self.assertEqual(body["tx_ref"], payment.reference)
        self.assertEqual(body["email"], self.user.email)
        self.assertTrue(body["return_url"].endswith(
            reverse("payment_return", args=[payment.order_list_id])
        ))

    def test_user_without_names_gets_fallback_names_for_chapa(self):
        self.checkout(tea=1)
        body = self.post.call_args.kwargs["json"]
        self.assertTrue(body["first_name"])
        self.assertTrue(body["last_name"])

    # -- Chapa failures
    def test_chapa_unreachable_cancels_order_and_restores_stock(self):
        self.post.side_effect = requests.ConnectionError("down")
        response = self.checkout(latte=3)

        self.assertRedirects(response, reverse("item_list"), fetch_redirect_response=False)
        self.assertEqual(
            messages_of(response)[-1],
            ("error", "Could not reach the payment service. Please try again."),
        )
        self.assertEqual(OrderList.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.latte.refresh_from_db()
        self.assertEqual(self.latte.stock_amount, 10)

    def test_chapa_rejection_cancels_order(self):
        bad = mock.Mock()
        bad.json.return_value = {"status": "failed", "message": "Invalid key"}
        self.post.return_value = bad

        response = self.checkout(latte=1)
        self.assertEqual(
            messages_of(response)[-1],
            ("error", "The payment service rejected the request."),
        )
        self.assertEqual(OrderList.objects.count(), 0)
        self.latte.refresh_from_db()
        self.assertEqual(self.latte.stock_amount, 10)

    @override_settings(CHAPA_SECRET_KEY="")
    def test_missing_api_key_cancels_order_without_calling_chapa(self):
        response = self.checkout(latte=1)
        self.assertIn("CHAPA_SECRET_KEY", messages_of(response)[-1][1])
        self.post.assert_not_called()
        self.assertEqual(OrderList.objects.count(), 0)
        self.latte.refresh_from_db()
        self.assertEqual(self.latte.stock_amount, 10)


# ----------------------------------------------------------- Chapa helpers

@override_settings(CHAPA_SECRET_KEY="CHASECK_TEST-abc")
class ChapaHelperTests(TestCase):
    def setUp(self):
        user = make_user()
        self.item = make_item("Latte", "50.00", stock=10)
        self.order_list, self.payment = make_order(user, [(self.item, 2)], reference="REF1")

    @mock.patch("coffeshopapp.views.requests.get")
    def test_verify_true_when_paid_and_amount_matches(self, get):
        get.return_value = chapa_verify_response(amount="100.00")
        self.assertTrue(views._chapa_verify(self.payment))
        self.assertEqual(
            get.call_args.args[0],
            "https://api.chapa.co/v1/transaction/verify/REF1",
        )

    @mock.patch("coffeshopapp.views.requests.get")
    def test_verify_accepts_numeric_amount(self, get):
        get.return_value = chapa_verify_response(amount=100)
        self.assertTrue(views._chapa_verify(self.payment))

    @mock.patch("coffeshopapp.views.requests.get")
    def test_verify_false_when_amount_differs(self, get):
        get.return_value = chapa_verify_response(amount="10.00")
        self.assertFalse(views._chapa_verify(self.payment))

    @mock.patch("coffeshopapp.views.requests.get")
    def test_verify_false_when_not_paid(self, get):
        get.return_value = chapa_verify_response(status="pending")
        self.assertFalse(views._chapa_verify(self.payment))
        get.return_value = chapa_verify_response(status="failed", outer="failed")
        self.assertFalse(views._chapa_verify(self.payment))

    @mock.patch("coffeshopapp.views.requests.get")
    def test_verify_false_on_garbage_response(self, get):
        bad = mock.Mock()
        bad.json.side_effect = ValueError("not json")
        get.return_value = bad
        self.assertFalse(views._chapa_verify(self.payment))

    @mock.patch("coffeshopapp.views.requests.get")
    def test_verify_raises_when_chapa_unreachable(self, get):
        get.side_effect = requests.Timeout("slow")
        with self.assertRaises(views.ChapaError):
            views._chapa_verify(self.payment)

    def test_cancel_order_restores_stock_and_removes_everything(self):
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_amount, 8)

        views._cancel_order(self.order_list)

        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_amount, 10)
        self.assertEqual(OrderList.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)


# ---------------------------------------------------------- payment return

@override_settings(CHAPA_SECRET_KEY="CHASECK_TEST-abc")
class PaymentReturnTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.item = make_item("Latte", "50.00", stock=10)
        self.order_list, self.payment = make_order(self.user, [(self.item, 2)], reference="REF1")
        self.url = reverse("payment_return", args=[self.order_list.pk])

        patcher = mock.patch("coffeshopapp.views.requests.get")
        self.get = patcher.start()
        self.addCleanup(patcher.stop)

    def test_paid_order_is_kept_and_user_sent_to_tracking(self):
        self.get.return_value = chapa_verify_response(amount="100.00")
        response = self.client.get(self.url)

        self.assertRedirects(response, reverse("track_order"), fetch_redirect_response=False)
        self.assertEqual(messages_of(response)[-1][0], "success")
        self.assertTrue(OrderList.objects.filter(pk=self.order_list.pk).exists())
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_amount, 8)

    def test_return_url_still_works_with_chapa_query_params(self):
        self.get.return_value = chapa_verify_response(amount="100.00")
        response = self.client.get(self.url + "?trx_ref=REF1&status=success")
        self.assertRedirects(response, reverse("track_order"), fetch_redirect_response=False)

    def test_unpaid_order_is_cancelled_and_stock_restored(self):
        self.get.return_value = chapa_verify_response(status="failed", outer="failed")
        response = self.client.get(self.url)

        self.assertRedirects(response, reverse("item_list"), fetch_redirect_response=False)
        self.assertEqual(messages_of(response)[-1][0], "error")
        self.assertEqual(OrderList.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_amount, 10)

    def test_amount_mismatch_is_treated_as_unpaid(self):
        self.get.return_value = chapa_verify_response(amount="1.00")
        self.client.get(self.url)
        self.assertEqual(OrderList.objects.count(), 0)

    def test_network_error_keeps_the_order(self):
        self.get.side_effect = requests.ConnectionError("down")
        response = self.client.get(self.url)

        self.assertRedirects(response, reverse("track_order"), fetch_redirect_response=False)
        self.assertEqual(messages_of(response)[-1][0], "error")
        self.assertTrue(OrderList.objects.filter(pk=self.order_list.pk).exists())
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_amount, 8)

    def test_cannot_touch_another_users_order(self):
        other = make_user("other@example.com")
        self.client.force_login(other)
        response = self.client.get(self.url)

        self.assertRedirects(response, reverse("item_list"), fetch_redirect_response=False)
        self.get.assert_not_called()
        self.assertTrue(OrderList.objects.filter(pk=self.order_list.pk).exists())

    def test_unknown_order_redirects_to_menu(self):
        response = self.client.get(reverse("payment_return", args=[99999]))
        self.assertRedirects(response, reverse("item_list"), fetch_redirect_response=False)
        self.assertEqual(messages_of(response)[-1][0], "error")


# --------------------------------------------------- track / history pages

class OrderPagesTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user("other@example.com")
        self.client.force_login(self.user)
        item = make_item(stock=100)

        self.open_order, _ = make_order(self.user, [(item, 1)], reference="A1")
        self.done_order, _ = make_order(
            self.user, [(item, 1)], reference="A2", status=OrderList.Status.FINISHED
        )
        self.others_order, _ = make_order(self.other, [(item, 1)], reference="A3")

    def test_track_order_shows_only_my_in_progress_orders(self):
        response = self.client.get(reverse("track_order"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["orders"]), [self.open_order])

    def test_order_history_shows_only_my_finished_orders(self):
        response = self.client.get(reverse("order_history"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["orders"]), [self.done_order])

    def test_orders_are_newest_first(self):
        item = Item.objects.get()
        newer, _ = make_order(self.user, [(item, 1)], reference="A4")
        response = self.client.get(reverse("track_order"))
        self.assertEqual(list(response.context["orders"]), [newer, self.open_order])


# -------------------------------------------------------- staff: stock page

class StockManagementTests(TestCase):
    def setUp(self):
        self.client.force_login(make_staff())
        self.latte = make_item("Latte", stock=10)
        self.tea = make_item("Tea", stock=5)
        self.url = reverse("stock_management")

    def test_page_lists_items(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([i.name for i in response.context["items"]], ["Latte", "Tea"])

    def test_updates_changed_items_only(self):
        response = self.client.post(self.url, {
            f"stock_{self.latte.pk}": "25",
            f"stock_{self.tea.pk}": "5",  # unchanged
        })
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertIn(("success", "Stock saved (1 item changed)."), messages_of(response))
        self.latte.refresh_from_db()
        self.tea.refresh_from_db()
        self.assertEqual(self.latte.stock_amount, 25)
        self.assertEqual(self.tea.stock_amount, 5)

    def test_message_pluralises(self):
        response = self.client.post(self.url, {
            f"stock_{self.latte.pk}": "1",
            f"stock_{self.tea.pk}": "1",
        })
        self.assertIn(("success", "Stock saved (2 items changed)."), messages_of(response))

    def test_can_set_stock_to_zero(self):
        self.client.post(self.url, {f"stock_{self.latte.pk}": "0"})
        self.latte.refresh_from_db()
        self.assertEqual(self.latte.stock_amount, 0)

    def test_negative_or_non_numeric_value_rejects_whole_save(self):
        for bad in ("-1", "abc", ""):
            with self.subTest(bad=bad):
                response = self.client.post(self.url, {
                    f"stock_{self.latte.pk}": "99",   # valid, but must not be saved
                    f"stock_{self.tea.pk}": bad,
                })
                self.assertEqual(messages_of(response)[-1][0], "error")
                self.latte.refresh_from_db()
                self.tea.refresh_from_db()
                self.assertEqual(self.latte.stock_amount, 10)
                self.assertEqual(self.tea.stock_amount, 5)


# ------------------------------------------------- staff: order status page

class OrderStatusManagementTests(TestCase):
    def setUp(self):
        self.client.force_login(make_staff())
        self.customer = make_user()
        item = make_item(stock=100)
        self.open_order, _ = make_order(self.customer, [(item, 1)], reference="B1")
        self.done_order, _ = make_order(
            self.customer, [(item, 1)], reference="B2", status=OrderList.Status.FINISHED
        )
        self.url = reverse("order_status_management")

    def test_open_orders_are_listed_first(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        orders = list(response.context["orders"])
        self.assertEqual(orders[0], self.open_order)
        self.assertEqual(orders[-1], self.done_order)

    def test_mark_in_progress_order_as_finished(self):
        response = self.client.post(self.url, {"order_id": self.open_order.pk})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertIn(
            ("success", f"Order #{self.open_order.pk} marked as finished."),
            messages_of(response),
        )
        self.open_order.refresh_from_db()
        self.assertEqual(self.open_order.order_status, OrderList.Status.FINISHED)

    def test_already_finished_order_cannot_be_updated(self):
        response = self.client.post(self.url, {"order_id": self.done_order.pk})
        self.assertEqual(messages_of(response)[-1][0], "error")

    def test_bad_or_unknown_order_id(self):
        for value in ("abc", "", "99999"):
            with self.subTest(value=value):
                response = self.client.post(self.url, {"order_id": value})
                self.assertEqual(
                    messages_of(response)[-1],
                    ("error", "That order could not be updated."),
                )
        self.open_order.refresh_from_db()
        self.assertEqual(self.open_order.order_status, OrderList.Status.IN_PROGRESS)


# ------------------------------------------------------------ audit report

class PeriodStartTests(TestCase):
    def test_periods_are_midnight_and_correctly_ordered(self):
        today = views._period_start("today")
        week = views._period_start("week")
        month = views._period_start("month")
        year = views._period_start("year")

        self.assertEqual((today.hour, today.minute, today.second), (0, 0, 0))
        self.assertEqual(week.weekday(), 0)               # Monday
        self.assertEqual(month.day, 1)
        self.assertEqual((year.month, year.day), (1, 1))
        self.assertLessEqual(week, today)
        self.assertLessEqual(month, today)
        self.assertLessEqual(year, month)

    def test_unknown_range_falls_back_to_today(self):
        self.assertEqual(views._period_start("nonsense"), views._period_start("today"))


class AuditTests(TestCase):
    def setUp(self):
        self.client.force_login(make_staff())
        self.alice = make_user("alice@example.com")
        self.bob = make_user("bob@example.com")
        self.item = make_item("Latte", "50.00", stock=1000)

    def backdate(self, order_list, when):
        """created_at is auto_now_add, so move it with a queryset update."""
        OrderList.objects.filter(pk=order_list.pk).update(created_at=when)
        Payment.objects.filter(order_list=order_list).update(created_at=when)

    def test_report_page_shows_todays_stats(self):
        make_order(self.alice, [(self.item, 2)], reference="C1")
        response = self.client.get(reverse("audit_report"))
        self.assertEqual(response.status_code, 200)
        stats = response.context["stats"]
        self.assertEqual(stats["orders"], 1)
        self.assertEqual(stats["users"], 1)
        self.assertEqual(stats["revenue"], Decimal("100.00"))

    def test_stats_are_zero_when_nothing_ordered(self):
        stats = views._audit_stats("today")
        self.assertEqual(stats, {"orders": 0, "users": 0, "revenue": Decimal("0")})

    def test_users_counts_distinct_customers(self):
        make_order(self.alice, [(self.item, 1)], reference="C1")
        make_order(self.alice, [(self.item, 1)], reference="C2")
        make_order(self.bob, [(self.item, 1)], reference="C3")
        stats = views._audit_stats("today")
        self.assertEqual(stats["orders"], 3)
        self.assertEqual(stats["users"], 2)
        self.assertEqual(stats["revenue"], Decimal("150.00"))

    def test_orders_before_the_period_start_are_excluded(self):
        old, _ = make_order(self.alice, [(self.item, 1)], reference="C1")
        make_order(self.bob, [(self.item, 2)], reference="C2")
        self.backdate(old, views._period_start("today") - timedelta(seconds=1))

        today = views._audit_stats("today")
        self.assertEqual(today["orders"], 1)
        self.assertEqual(today["revenue"], Decimal("100.00"))

        # …but a wider period still includes it when it falls inside it
        year_start = views._period_start("year")
        self.backdate(old, year_start)  # boundary is inclusive
        self.assertEqual(views._audit_stats("year")["orders"], 2)

    def test_year_excludes_last_years_orders(self):
        old, _ = make_order(self.alice, [(self.item, 1)], reference="C1")
        self.backdate(old, views._period_start("year") - timedelta(seconds=1))
        self.assertEqual(views._audit_stats("year")["orders"], 0)

    def test_stats_endpoint_returns_json(self):
        make_order(self.alice, [(self.item, 3)], reference="C1")
        response = self.client.get(reverse("audit_stats"), {"range": "today"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["orders"], 1)
        self.assertEqual(data["users"], 1)
        self.assertEqual(Decimal(data["revenue"]), Decimal("150"))
        self.assertIsInstance(data["revenue"], str)

    def test_stats_endpoint_accepts_every_range_and_defaults_to_today(self):
        for rng in ("today", "week", "month", "year", "bogus"):
            with self.subTest(range=rng):
                self.assertEqual(
                    self.client.get(reverse("audit_stats"), {"range": rng}).status_code, 200
                )
        self.assertEqual(self.client.get(reverse("audit_stats")).status_code, 200)

    def test_stats_endpoint_is_get_only(self):
        self.assertEqual(self.client.post(reverse("audit_stats")).status_code, 405)


# ------------------------------------------------------------------- admin

class AdminSmokeTests(TestCase):
    """Every registered changelist should at least load."""

    def test_changelists_load_for_superuser(self):
        admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.client.force_login(admin)
        for model in ("user", "item", "orderlist", "payment"):
            with self.subTest(model=model):
                url = reverse(f"admin:coffeshopapp_{model}_changelist")
                self.assertEqual(self.client.get(url).status_code, 200)