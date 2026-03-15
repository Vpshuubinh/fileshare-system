// Soft fade/slide animation for the auth card
const card = document.getElementById("authCard");
if (card) {
  card.style.opacity = "0";
  card.style.transform = "translateY(18px)";
  requestAnimationFrame(() => {
    card.style.transition = "all 0.4s ease";
    card.style.opacity = "1";
    card.style.transform = "translateY(0)";
  });
}

// Loading state on submit
document.querySelectorAll(".auth-form").forEach((form) => {
  const btn = form.querySelector(".btn-primary");
  if (!btn) return;
  form.addEventListener("submit", () => {
    btn.dataset.label = btn.dataset.label || btn.textContent.trim();
    btn.classList.remove("success");
    btn.classList.add("loading");
    btn.textContent = "Đang xử lý...";
  });

  const successMsg = form.parentElement?.querySelector(".flash .success");
  if (successMsg) {
    btn.classList.remove("loading");
    btn.classList.add("success");
    btn.textContent = "Thành công!";
  }
});

// Toast for flashed messages on auth pages (shows top-right, auto hide)
const flashMount = document.querySelector(".toast-mount");
if (flashMount) {
  try {
    const messages = JSON.parse(flashMount.dataset.flash || "[]");
    if (messages.length) {
      const stack = document.querySelector(".toast-stack-auth") || (() => {
        const s = document.createElement("div");
        s.className = "toast-stack-auth";
        document.body.appendChild(s);
        return s;
      })();
      messages.forEach(([category, message]) => {
        const t = document.createElement("div");
        t.className = "toast-auth";
        t.textContent = message;
        if (category === "error") t.style.background = "#b91c1c";
        if (category === "success") t.style.background = "#16a34a";
        stack.appendChild(t);
        setTimeout(() => t.remove(), 3000);
      });
    }
  } catch (e) {
    // ignore json parse errors
  }
}

// Password visibility toggles & random generator
const pwdInput = document.querySelector("input[data-password]");
const confirmInput = document.querySelector("input[data-confirm]");
const togglePwd = document.querySelector("[data-toggle]");
const toggleConfirm = document.querySelector("[data-toggle-confirm]");
const randomBtn = document.querySelector("[data-random]");

function toggleVisibility(input, btn) {
  if (!input || !btn) return;
  const isPwd = input.type === "password";
  input.type = isPwd ? "text" : "password";
  btn.textContent = isPwd ? "Ẩn" : "Hiện";
}
if (togglePwd) {
  togglePwd.addEventListener("click", () => toggleVisibility(pwdInput, togglePwd));
}
if (toggleConfirm) {
  toggleConfirm.addEventListener("click", () => toggleVisibility(confirmInput, toggleConfirm));
}
if (randomBtn && pwdInput && confirmInput) {
  randomBtn.addEventListener("click", () => {
    const charset = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@$%?";
    let pw = "";
    for (let i = 0; i < 12; i++) pw += charset[Math.floor(Math.random() * charset.length)];
    pwdInput.value = pw;
    confirmInput.value = pw;
  });
}
