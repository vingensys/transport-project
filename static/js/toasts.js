// static/js/toasts.js
document.addEventListener("DOMContentLoaded", function () {
  if (!window.FLASH_MESSAGES) return;

  const container = document.getElementById("toast-container");
  if (!container) return;

  window.FLASH_MESSAGES.forEach(msg => {
    const toastEl = document.createElement("div");

    toastEl.className =
      "toast align-items-center text-bg-" +
      msg.category +
      " border-0";

    toastEl.setAttribute("role", "alert");
    toastEl.setAttribute("aria-live", "assertive");
    toastEl.setAttribute("aria-atomic", "true");

    toastEl.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">${msg.message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto"
                data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    `;

    container.appendChild(toastEl);

    const t = new bootstrap.Toast(toastEl, { delay: 4000 });
    t.show();
  });
});
