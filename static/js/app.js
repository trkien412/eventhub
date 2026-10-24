/* Tương tác nhỏ, không phụ thuộc thư viện ngoài. */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var navToggle = document.getElementById("nav-toggle");
    if (navToggle) {
      document.querySelectorAll(".main-nav a, .main-nav button").forEach(function (el) {
        el.addEventListener("click", function () {
          navToggle.checked = false;
        });
      });
    }

    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.getAttribute("data-confirm"))) {
          event.preventDefault();
        }
      });
    });

    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        var value = button.getAttribute("data-copy");
        if (!value || !navigator.clipboard) {
          return;
        }
        navigator.clipboard.writeText(value).then(function () {
          var original = button.textContent;
          button.textContent = "Đã sao chép";
          window.setTimeout(function () {
            button.textContent = original;
          }, 1800);
        });
      });
    });

    document.querySelectorAll("[data-dismiss-alert]").forEach(function (button) {
      button.addEventListener("click", function () {
        var alert = button.closest(".alert");
        if (alert) {
          alert.remove();
        }
      });
    });

    window.setTimeout(function () {
      document.querySelectorAll(".messages .alert").forEach(function (alert) {
        alert.classList.add("is-hiding");
        window.setTimeout(function () {
          alert.remove();
        }, 300);
      });
    }, 7000);
  });
})();
