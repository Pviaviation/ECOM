/* =========================================================
   script.js — tương tác nhẹ (vanilla JS, không framework)
   - Menu mobile
   - Scroll-spy làm nổi mục lục
   - Smooth-scroll + đóng menu khi chọn
   - Nút In / xuất PDF
   - Năm bản quyền tự động
   ========================================================= */

(function () {
  "use strict";

  /* ---- Năm bản quyền ---- */
  var yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  /* ---- Menu mobile ---- */
  var toggle = document.getElementById("navToggle");
  var links = document.getElementById("navLinks");

  function closeMenu() {
    if (!links || !toggle) return;
    links.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
  }

  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    links.addEventListener("click", function (e) {
      if (e.target.tagName === "A") closeMenu();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeMenu();
    });
  }

  /* ---- Nút In / xuất PDF ---- */
  var printBtn = document.getElementById("printBtn");
  if (printBtn) {
    printBtn.addEventListener("click", function () {
      window.print();
    });
  }

  /* ---- Scroll-spy cho mục lục ---- */
  var tocLinks = Array.prototype.slice.call(
    document.querySelectorAll("#toc a")
  );
  var sections = tocLinks
    .map(function (a) {
      var id = a.getAttribute("href").slice(1);
      return document.getElementById(id);
    })
    .filter(Boolean);

  if ("IntersectionObserver" in window && sections.length) {
    var setActive = function (id) {
      tocLinks.forEach(function (a) {
        a.classList.toggle("is-active", a.getAttribute("href") === "#" + id);
      });
    };

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) setActive(entry.target.id);
        });
      },
      { rootMargin: "-45% 0px -50% 0px", threshold: 0 }
    );

    sections.forEach(function (sec) {
      observer.observe(sec);
    });
  }

  /* ---- Scroll reveal cho từng section (chuyển cảnh mượt) ---- */
  var blocks = Array.prototype.slice.call(document.querySelectorAll(".block"));
  if (blocks.length) {
    if ("IntersectionObserver" in window) {
      document.documentElement.classList.add("reveal-ready");
      var revealObs = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              entry.target.classList.add("in-view");
              revealObs.unobserve(entry.target);
            }
          });
        },
        { rootMargin: "0px 0px -10% 0px", threshold: 0.06 }
      );
      blocks.forEach(function (b) { revealObs.observe(b); });

      /* Lưới an toàn: bất kỳ block nào đã nằm trong/đi qua viewport
         đều được hiện ngay (tránh ẩn khi deep-link, khôi phục vị trí cuộn,
         hoặc cuộn/nhảy quá nhanh). */
      var safetyReveal = function () {
        var vh = window.innerHeight || document.documentElement.clientHeight;
        blocks.forEach(function (b) {
          if (b.classList.contains("in-view")) return;
          var r = b.getBoundingClientRect();
          if (r.top < vh * 0.92) {
            b.classList.add("in-view");
            revealObs.unobserve(b);
          }
        });
      };
      window.addEventListener("scroll", safetyReveal, { passive: true });
      window.addEventListener("load", safetyReveal);
      window.addEventListener("hashchange", function () {
        setTimeout(safetyReveal, 60);
      });
      setTimeout(safetyReveal, 400);
    }
  }
})();
