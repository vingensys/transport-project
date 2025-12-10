// static/js/route.js

document.addEventListener("DOMContentLoaded", function () {

  function extractCode(raw) {
    if (!raw) return "";
    raw = raw.trim();
    const start = raw.indexOf("[");
    const end = raw.indexOf("]");
    if (start !== -1 && end !== -1 && end > start + 1) {
      return raw.substring(start + 1, end).trim();
    }
    return raw; // fallback: user typed pure code
  }

  function setupPanel(panelKey, listId) {
    const input = document.querySelector(`input[data-role="${panelKey}-input"]`);
    const button = document.querySelector(`button[data-role="${panelKey}-add"]`);
    const list = document.getElementById(listId);

    if (!input || !button || !list) return;

    function addItem() {
      const raw = input.value;
      const code = extractCode(raw).toUpperCase();
      if (!code) return;

      const li = document.createElement("li");
      li.className = "list-group-item d-flex justify-content-between align-items-center";

      const span = document.createElement("span");
      span.textContent = code;
      li.appendChild(span);

      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = panelKey + "_locations[]";
      hidden.value = code;
      li.appendChild(hidden);

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "btn btn-sm btn-link text-danger ms-2";
      removeBtn.textContent = "×";
      removeBtn.addEventListener("click", function () {
        li.remove();
      });
      li.appendChild(removeBtn);

      list.appendChild(li);
      input.value = "";
      input.focus();
    }

    button.addEventListener("click", addItem);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        addItem();
      }
    });
  }

  setupPanel("from", "fromLocationList");
  setupPanel("mid", "midLocationList");
  setupPanel("to", "toLocationList");

});
