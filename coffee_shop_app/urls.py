from django.urls import path

from . import views

urlpatterns = [
    path("", views.item_list, name="item_list"),
    path("sign-in/", views.SignInView.as_view(), name="sign_in"),
    path("sign-out/", views.SignOutView.as_view(), name="sign_out"),
    path("sign-up/", views.sign_up, name="sign_up"),

    # Customer pages
    path("orders/", views.order_history, name="order_history"),
    path("orders/track/", views.track_order, name="track_order"),

    # Admin pages (staff only)
    path("manage/stock/", views.stock_management, name="stock_management"),
    path("manage/orders/", views.order_status_management, name="order_status_management"),
    path("audit/", views.audit_report, name="audit_report"),
    path("audit/stats/", views.audit_stats, name="audit_stats"),
    path("payment/return/<int:pk>/", views.payment_return, name="payment_return")
]