// Shared utilities -----------------------------------------------------
const toastStack =
  document.getElementById("toastStack") ||
  (() => {
    const stack = document.createElement("div");
    stack.id = "toastStack";
    stack.className = "toast-stack";
    document.body.appendChild(stack);
    return stack;
  })();

function showToast(msg) {
  if (!toastStack) return;
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  toastStack.appendChild(t);
  setTimeout(() => t.remove(), 5000);
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

// Copy link buttons (dashboard + recent)
document.addEventListener("click", (e) => {
  if (e.target.matches("[data-copy]")) {
    const text = e.target.dataset.copy;
    navigator.clipboard.writeText(text).then(() => showToast("Đã copy link"));
  }
});

// Landing upload with drag/drop + progress -----------------------------
const dropArea = document.getElementById("landingDrop");
const fileInput = document.getElementById("landingFileInput");
const statusBox = document.getElementById("landingStatus");
const selectedBox = document.getElementById("selectedFile");
const fileNameEl = document.getElementById("fileName");
const fileSizeEl = document.getElementById("fileSize");
const uploadBtn = document.getElementById("uploadBtn");
const removeBtn = document.getElementById("removeFile");
const modal = document.getElementById("optionsModal");
const modalPassword = document.getElementById("modalPassword");
const modalExpire = document.getElementById("modalExpire");
const modalCancel = document.getElementById("modalCancel");
const modalConfirm = document.getElementById("modalConfirm");
const progressBar = document.getElementById("uploadProgress");
let pendingFile = null;

function setStatus(msg, type = "info") {
  if (!statusBox) return;
  statusBox.textContent = msg;
  statusBox.className = `status ${type}`;
}

function showSelected(file) {
  pendingFile = file;
  fileNameEl.textContent = file.name;
  fileSizeEl.textContent = formatSize(file.size);
  selectedBox.classList.remove("hidden");
  setStatus("");
}

function clearSelected() {
  pendingFile = null;
  selectedBox?.classList.add("hidden");
  fileInput && (fileInput.value = "");
  if (progressBar) {
    progressBar.style.width = "0%";
    progressBar.parentElement?.classList.add("hidden");
  }
}

function openModal() {
  modal?.classList.remove("hidden");
}
function closeModal() {
  modal?.classList.add("hidden");
}

function uploadFile(file, password, expireHours) {
  if (!file) return;
  const maxBytes = 500 * 1024 * 1024;
  if (file.size > maxBytes) {
    setStatus("File vượt 500MB. Vui lòng chọn file nhỏ hơn.", "error");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  if (password) formData.append("link_password", password);
  formData.append("expire_hours", expireHours);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/upload-ajax");
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable || !progressBar) return;
    const percent = Math.round((e.loaded / e.total) * 100);
    progressBar.style.width = `${percent}%`;
    progressBar.parentElement.classList.remove("hidden");
    setStatus(`Đang tải lên... ${percent}%`, "info");
  };
  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      const data = JSON.parse(xhr.responseText);
      setStatus("");
      const recentList = document.querySelector(".recent-list");
      if (recentList) {
        const card = document.createElement("div");
        card.className = "recent-card";
        card.innerHTML = `
          <div class="row">
            <div class="icon-file">📄</div>
            <div>
              <div class="name">${data.filename}</div>
              <div class="muted">${formatSize(data.size)}</div>
            </div>
          </div>
          <div class="row space">
            <div class="tags">
              ${data.password ? '<span class="tag warn">Có mật khẩu</span>' : ""}
              <span class="tag light">${data.expire_hours}h</span>
            </div>
            <button class="btn-secondary copy-btn" data-copy="${data.link}">Copy link</button>
          </div>
        `;
        recentList.prepend(card);
      }
      showToast("Upload thành công! Link đã sẵn sàng");
      clearSelected();
      closeModal();
    } else {
      setStatus("Upload thất bại", "error");
      closeModal();
    }
  };
  xhr.onerror = () => {
    setStatus("Lỗi mạng khi upload", "error");
    closeModal();
  };
  xhr.send(formData);
}

if (dropArea) {
  dropArea.addEventListener("click", (e) => {
    if (e.target.closest(".selected")) return;
    fileInput && fileInput.click();
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
    if (file) showSelected(file);
  });
}

fileInput?.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (file) showSelected(file);
});

removeBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  clearSelected();
});

uploadBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  if (!pendingFile) return setStatus("Chưa chọn file", "error");
  openModal();
});
modalCancel?.addEventListener("click", (e) => {
  e.stopPropagation();
  closeModal();
});
modalConfirm?.addEventListener("click", (e) => {
  e.stopPropagation();
  uploadFile(pendingFile, modalPassword?.value.trim(), modalExpire?.value);
});

// --- Ad banner helpers for download page ---
document.addEventListener("DOMContentLoaded", () => {
  const placeholderSvg = encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="200" viewBox="0 0 1200 200" fill="none">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
          <stop stop-color="#1f8bff" offset="0%"/>
          <stop stop-color="#14d6d6" offset="100%"/>
        </linearGradient>
      </defs>
      <rect width="1200" height="200" rx="16" fill="url(#g)"/>
      <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="Inter, Arial" font-size="32" font-weight="700" fill="#fff">
        Quảng cáo VPSHUUBINHTM - Thuê VPS chỉ từ 75k/tháng
      </text>
    </svg>`
  );
  const placeholder = `data:image/svg+xml;charset=utf-8,${placeholderSvg}`;

  document.querySelectorAll(".ad-banner img").forEach((img) => {
    const markLoaded = () => img.classList.add("is-loaded");
    const handleError = () => {
      if (img.dataset.fallbacked) return;
      img.dataset.fallbacked = "1";
      img.src = placeholder;
    };
    if (img.complete) {
      if (img.naturalWidth) markLoaded();
      else handleError();
    } else {
      img.addEventListener("load", markLoaded, { once: true });
      img.addEventListener("error", handleError, { once: true });
    }
  });
});
