/* ==========================================================
   Aka Coffee - consolidated JavaScript
   Each block only runs if its page's form exists, so this one
   file can be loaded on every page.
   Client-side checks are for convenience; Django validates
   everything again on the server.
   ========================================================== */
(function () {
    "use strict";

    // Stop the submit, show a message, focus the offending field.
    function invalid(event, errorEl, field, text) {
        event.preventDefault();
        errorEl.textContent = text;
        field.focus();
    }

    /* ---------- Sign in ---------- */
    (function initSignIn() {
        var form = document.getElementById("loginForm");
        if (!form) return;

        form.addEventListener("submit", function (e) {
            var email = document.getElementById("email");
            var password = document.getElementById("password");
            var error = document.getElementById("error");

            if (!email.value.trim() || !email.checkValidity()) {
                return invalid(e, error, email, "Enter a valid email address.");
            }
            if (!password.value) {
                return invalid(e, error, password, "Enter your password.");
            }
            error.textContent = "";
        });
    })();

    /* ---------- Sign up ---------- */
    (function initSignUp() {
        var form = document.getElementById("signupForm");
        if (!form) return;

        form.addEventListener("submit", function (e) {
            var first = document.getElementById("firstName");
            var last = document.getElementById("lastName");
            var email = document.getElementById("email");
            var phone = document.getElementById("phone");
            var password = document.getElementById("password");
            var confirm = document.getElementById("confirmPassword");
            var error = document.getElementById("error");
            var digits = phone.value.replace(/[\s\-()+]/g, "");

            if (!first.value.trim()) {
                return invalid(e, error, first, "Enter your first name.");
            }
            if (!last.value.trim()) {
                return invalid(e, error, last, "Enter your last name.");
            }
            if (!email.value.trim() || !email.checkValidity()) {
                return invalid(e, error, email, "Enter a valid email address.");
            }
            if (!/^\d{9,15}$/.test(digits)) {
                return invalid(e, error, phone, "Enter a valid phone number.");
            }
            if (password.value.length < 8) {
                return invalid(e, error, password, "Password must be at least 8 characters.");
            }
            if (password.value !== confirm.value) {
                return invalid(e, error, confirm, "Passwords do not match.");
            }
            error.textContent = "";
        });
    })();

    /* ---------- Item list / place order ---------- */
    (function initOrder() {
        var form = document.getElementById("orderForm");
        if (!form) return;

        var list = document.getElementById("items");
        if (!list) return; // the menu page uses initMenu below instead

        var totalEl = document.getElementById("total");
        var placeBtn = document.getElementById("place");
        var msg = document.getElementById("msg");
        var rows = list.querySelectorAll(".item[data-price]");

        function refresh() {
            var total = 0;
            rows.forEach(function (row) {
                var input = row.querySelector('input[type="hidden"]');
                var n = Number(input.value) || 0;
                row.querySelector("output").textContent = n;
                total += n * Number(row.dataset.price);
            });
            total = Math.round(total * 100) / 100;
            totalEl.textContent = total + " Birr";
            placeBtn.disabled = total === 0;
            return total;
        }

        list.addEventListener("click", function (e) {
            var b = e.target.closest("button[data-d]");
            if (!b) return;
            var row = b.closest(".item");
            var input = row.querySelector('input[type="hidden"]');
            var stock = Number(row.dataset.stock);
            var next = (Number(input.value) || 0) + Number(b.dataset.d);
            input.value = Math.min(stock, Math.max(0, next));
            msg.textContent = "";
            refresh();
        });

        form.addEventListener("submit", function (e) {
            if (refresh() === 0) {
                e.preventDefault();
                return;
            }
            placeBtn.disabled = true; // prevent double submit
        });

        // Also runs when the browser restores the page via Back button
        window.addEventListener("pageshow", refresh);
        refresh();
    })();

    /* ---------- Admin dropdown: close on outside click / Escape ---------- */
    (function initDropdown() {
        var dd = document.querySelector("details.dropdown");
        if (!dd) return;
        document.addEventListener("click", function (e) {
            if (!dd.contains(e.target)) dd.removeAttribute("open");
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") dd.removeAttribute("open");
        });
    })();

    /* ---------- Menu: search + order preview pop-up ---------- */
    (function initMenu() {
        var form = document.getElementById("orderForm");
        if (!form) return;

        var rows = Array.prototype.slice.call(form.querySelectorAll(".order-row[data-price]"));
        var search = document.getElementById("itemSearch");
        var noMatch = document.getElementById("noMatch");
        var reviewBtn = document.getElementById("reviewBtn");
        var error = document.getElementById("orderError");
        var dialog = document.getElementById("previewDialog");
        var list = document.getElementById("previewList");
        var totalEl = document.getElementById("previewTotal");
        var back = document.getElementById("previewBack");
        var checkoutBtn = document.getElementById("checkoutBtn");

        function money(n) { return (Math.round(n * 100) / 100).toFixed(2) + " ETB"; }

        // Search by name (rows stay in the form, so hidden ones keep their quantity)
        if (search) {
            search.addEventListener("input", function () {
                var q = search.value.trim().toLowerCase();
                var shown = 0;
                rows.forEach(function (row) {
                    var match = row.dataset.name.indexOf(q) !== -1;
                    row.hidden = !match;
                    if (match) shown++;
                });
                if (noMatch) noMatch.hidden = shown !== 0 || rows.length === 0;
            });
        }

        // Quantity typed by the user (0 if empty/invalid/disabled). Not clamped,
        // so over-stock requests can be reported instead of silently changed.
        function qtyOf(row) {
            var input = row.querySelector(".qty-input");
            if (!input || input.disabled) return 0;
            return Math.max(0, Math.floor(Number(input.value)) || 0);
        }

        if (!reviewBtn || !dialog) return;

        reviewBtn.addEventListener("click", function () {
            var total = 0;
            var problem = "";
            list.textContent = "";

            rows.forEach(function (row) {
                var n = qtyOf(row);
                if (n === 0) return;

                var input = row.querySelector(".qty-input");
                var max = Number(input.max);
                if (!problem && !isNaN(max) && n > max) {
                    problem = "Only " + max + " left of " + row.dataset.label + ".";
                    input.focus();
                }

                var price = Number(row.dataset.price);
                var sub = n * price;
                total += sub;

                var li = document.createElement("li");
                var left = document.createElement("span");
                var name = document.createElement("strong");
                var meta = document.createElement("span");
                var right = document.createElement("span");

                name.textContent = row.dataset.label;
                meta.className = "line-meta";
                meta.textContent = n + " \u00d7 " + money(price);
                left.appendChild(name);
                left.appendChild(meta);
                right.textContent = money(sub);

                li.appendChild(left);
                li.appendChild(right);
                list.appendChild(li);
            });

            if (total === 0) {
                error.textContent = "Choose at least one item first.";
                return;
            }
            if (problem) {
                error.textContent = problem;
                return;
            }
            error.textContent = "";
            totalEl.textContent = money(total);
            dialog.showModal();
        });

        back.addEventListener("click", function () { dialog.close(); });

        // Click on the dark backdrop closes the pop-up
        dialog.addEventListener("click", function (e) {
            if (e.target === dialog) dialog.close();
        });

        // Enter in a quantity box opens the review instead of submitting the order
        form.addEventListener("keydown", function (e) {
            if (e.key === "Enter" && e.target.classList.contains("qty-input")) {
                e.preventDefault();
                reviewBtn.click();
            }
        });

        // Avoid double submit while the order is created and we redirect to Chapa
        form.addEventListener("submit", function () {
            if (!checkoutBtn) return;
            checkoutBtn.disabled = true;
            checkoutBtn.textContent = "Redirecting\u2026";
        });

        // Re-enable after Back-button page restore (coming back from Chapa)
        window.addEventListener("pageshow", function () {
            if (checkoutBtn) {
                checkoutBtn.disabled = false;
                checkoutBtn.textContent = "Checkout with Chapa";
            }
            if (dialog.open) dialog.close();
        });
    })();

    /* ---------- Admin: audit report filter (live update) ---------- */
    (function initAudit() {
        var wrap = document.getElementById("auditWrap");
        if (!wrap) return;

        var endpoint = wrap.dataset.endpoint;
        var buttons = wrap.querySelectorAll(".filter-btn");
        var ordersEl = document.getElementById("statOrders");
        var usersEl = document.getElementById("statUsers");
        var revenueEl = document.getElementById("statRevenue");
        var range = "today";

        function money(n) {
            return Number(n || 0).toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }) + " ETB";
        }

        function load() {
            if (!endpoint) return; // endpoint is wired up in the next phase
            fetch(endpoint + "?range=" + encodeURIComponent(range), {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin"
            })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    ordersEl.textContent = d.orders;
                    usersEl.textContent = d.users;
                    revenueEl.textContent = money(d.revenue);
                })
                .catch(function () { /* keep the last values */ });
        }

        buttons.forEach(function (b) {
            b.addEventListener("click", function () {
                buttons.forEach(function (x) { x.classList.remove("active"); });
                b.classList.add("active");
                range = b.dataset.range;
                load();
            });
        });

        // Keep the boxes fresh while the page stays open
        setInterval(load, 30000);
    })();

    /* ---------- Admin: stock management steppers ---------- */
    (function initStock() {
        var form = document.getElementById("stockForm");
        if (!form) return;

        function bump(input, delta) {
            var next = (Math.floor(Number(input.value)) || 0) + delta;
            input.value = Math.max(0, next);
        }

        form.addEventListener("click", function (e) {
            var b = e.target.closest("button[data-step]");
            if (!b) return;
            bump(b.parentNode.querySelector("input"), Number(b.dataset.step));
        });

        // Mouse-wheel scrolling changes the value while the field is focused
        form.addEventListener("wheel", function (e) {
            var input = e.target;
            if (input.type !== "number" || document.activeElement !== input) return;
            e.preventDefault();
            bump(input, e.deltaY < 0 ? 1 : -1);
        }, { passive: false });
    })();

    /* ---------- Admin: order status filter ---------- */
    (function initStatusFilter() {
        var bar = document.getElementById("statusFilter");
        if (!bar) return;

        var buttons = bar.querySelectorAll(".filter-btn");
        var cards = document.querySelectorAll(".status-row");

        buttons.forEach(function (b) {
            b.addEventListener("click", function () {
                buttons.forEach(function (x) { x.classList.remove("active"); });
                b.classList.add("active");
                cards.forEach(function (c) {
                    c.hidden = b.dataset.filter !== "all" && c.dataset.status !== b.dataset.filter;
                });
            });
        });
    })();
})();