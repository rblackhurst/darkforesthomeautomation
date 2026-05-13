// Disable submit button on form submission to prevent double-posts.
(function () {
  const form = document.querySelector("form");
  if (!form) return;
  form.addEventListener("submit", () => {
    const btn = form.querySelector(".submit-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Creating…";
    }
  });
})();
