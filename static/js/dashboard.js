const dropArea = document.querySelector("#quickUploadDrop .upload-box");
const fileInput = document.getElementById("quickFileInput");
const bar = document.getElementById("uploadProgressBar");
const toastStack =
  document.getElementById("toastStack") ||
  (() => {
    const s = document.createElement("div");
    s.id = "toastStack";
    s.className = "toast-stack";
    document.body.appendChild(s);
    return s;
  })();

function showToast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  toastStack.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

function setProgress(p) {
  if (!bar) return;
  bar.style.width = `${p}%`;
  bar.parentElement?.classList.remove("hidden");
}
function resetProgress() {
  if (!bar) return;
  bar.style.width = "0%";
  bar.parentElement?.classList.add("hidden");
}

if (dropArea) {
  dropArea.addEventListener("click", (e) => {
    if (e.target.closest("select")) return; // don't open file dialog when selecting expiry
    fileInput?.click();
  });
  ["dragover", "dragenter"].forEach((evt) =>
    dropArea.addEventListener(evt, (e) => {
      e.preventDefault();
      dropArea.classList.add("dragging");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropArea.addEventListener(evt, (e) => {
      e.preventDefault();
      dropArea.classList.remove("dragging");
    })
  );
  dropArea.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  });
}
fileInput?.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (file) uploadFile(file);
});

function uploadFile(file) {
  const max = 500 * 1024 * 1024;
  if (file.size > max) {
    showToast("File vượt 500MB");
    return;
  }
  const fd = new FormData();
  fd.append("file", file);
  const expSelect = document.getElementById("quickExpire");
  if (expSelect) fd.append("expire_hours", expSelect.value);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/upload-ajax");
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const pct = Math.round((e.loaded / e.total) * 100);
    setProgress(pct);
  };
  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      const data = JSON.parse(xhr.responseText);
      prependRow(data);
      showToast("Upload thành công");
    } else {
      showToast("Upload thất bại");
    }
    resetProgress();
  };
  xhr.onerror = () => {
    showToast("Lỗi mạng");
    resetProgress();
  };
  xhr.send(fd);
}

function prependRow(data) {
  const table = document.getElementById("fileTable");
  if (!table) return;
  const row = document.createElement("div");
  row.className = "row file-row";
  row.dataset.name = data.filename.toLowerCase();
  row.dataset.pwd = data.password ? "1" : "0";
  row.dataset.expire = new Date().toISOString(); // placeholder
  row.innerHTML = `
    <div class="cell name">
      <span class="file-icon">📄</span>
      <div>
        <p class="fname">${data.filename}</p>
        ${data.password ? '<span class="badge warn">Có mật khẩu</span>' : ""}
      </div>
    </div>
    <div class="cell"><p class="muted">Vừa xong</p></div>
    <div class="cell">--</div>
    <div class="cell"><span class="badge" data-exp-badge>24h</span></div>
    <div class="cell">0</div>
    <div class="cell actions">
      <button class="icon-btn" data-copy="${data.link}">🔗</button>
      <a class="icon-btn" href="${data.link}" target="_blank">👁</a>
    </div>
  `;
  table.prepend(row);
}

// Copy buttons
document.addEventListener("click", (e) => {
  if (e.target.matches("[data-copy]")) {
    const text = e.target.dataset.copy;
    navigator.clipboard.writeText(text).then(() => showToast("Đã copy link"));
  }
});

// Tabs filter
const tabs = document.querySelectorAll(".tab");
const rows = () => Array.from(document.querySelectorAll(".file-row"));
tabs.forEach((tab) =>
  tab.addEventListener("click", () => {
    tabs.forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const type = tab.dataset.filter;
    const now = Date.now();
    rows().forEach((r) => {
      const hasPwd = r.dataset.pwd === "1";
      const expire = new Date(r.dataset.expire).getTime();
      const hoursLeft = (expire - now) / 36e5;
      let show = true;
      if (type === "pwd") show = hasPwd;
      if (type === "exp") show = hoursLeft <= 12;
      r.style.display = show ? "grid" : "none";
    });
  })
);

// Search filter
const searchInput = document.getElementById("searchInput");
searchInput?.addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase();
  rows().forEach((r) => {
    r.style.display = r.dataset.name.includes(q) ? "grid" : "none";
  });
});

// Expire badge update
function updateExpireBadges() {
  const now = Date.now();
  document.querySelectorAll("[data-exp-badge]").forEach((badge) => {
    const parent = badge.closest(".file-row");
    const exp = new Date(parent.dataset.expire).getTime();
    const hours = Math.max(0, Math.round((exp - now) / 36e5));
    badge.textContent = hours > 0 ? `${hours}h` : "Hết hạn";
    badge.className = "badge";
    if (hours <= 6) badge.classList.add("danger");
    else if (hours <= 12) badge.classList.add("warn");
  });
}
updateExpireBadges();
setInterval(updateExpireBadges, 60000);
