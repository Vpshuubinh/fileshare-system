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
let pendingFile = null;
const toastStack = document.getElementById("toastStack");
const isLogged = (document.body.dataset.logged || "0") === "1";

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function setStatus(msg, type = "info") {
  if (!statusBox) return;
  statusBox.textContent = msg;
  statusBox.className = `status ${type}`;
}

function showToast(msg) {
  if (!toastStack) return;
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  toastStack.appendChild(t);
  setTimeout(() => t.remove(), 5000);
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
  selectedBox.classList.add("hidden");
  fileInput.value = "";
}

function openModal() {
  modal.classList.remove("hidden");
}
function closeModal() {
  modal.classList.add("hidden");
}

function uploadFile(file, password, expireHours) {
  if (!file) return;
  const maxBytes = 2 * 1024 * 1024 * 1024; // 2GB
  if (file.size > maxBytes) {
    setStatus("File vượt 2GB. Vui lòng chọn file nhỏ hơn.", "error");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  if (password) formData.append("link_password", password);
  formData.append("expire_hours", expireHours);
  setStatus("Đang tải lên...", "info");
  fetch("/upload-ajax", {
    method: "POST",
    body: formData,
  })
    .then(async (res) => {
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Lỗi tải lên");
      setStatus("");
      // prepend to recent list if available
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
        card.querySelector(".copy-btn").addEventListener("click", () => {
          navigator.clipboard.writeText(data.link).then(() => {
            showToast("Đã copy link");
          });
        });
      }
      showToast("Upload thành công! Link đã sẵn sàng");
      clearSelected();
    })
    .catch((err) => {
      setStatus(err.message, "error");
      showToast(err.message);
    })
    .finally(closeModal);
}

if (dropArea) {
  dropArea.addEventListener("click", (e) => {
    if (e.target.closest(".selected")) return; // avoid reopening picker when clicking controls
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

if (fileInput) {
  fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) showSelected(file);
  });
}

if (removeBtn) removeBtn.addEventListener("click", clearSelected);
if (uploadBtn)
  uploadBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!pendingFile) return setStatus("Chưa chọn file", "error");
    openModal();
  });
if (modalCancel) modalCancel.addEventListener("click", (e) => { e.stopPropagation(); closeModal(); });
if (modalConfirm)
  modalConfirm.addEventListener("click", (e) => {
    e.stopPropagation();
    let expireVal = modalExpire.value;
    if (expireVal === "0" && !isLogged) {
      showToast("Bạn cần đăng nhập để chọn lưu trữ vĩnh viễn.");
      setStatus("Chỉ tài khoản đã đăng nhập mới chọn được chế độ vĩnh viễn.", "error");
      return;
    }
    uploadFile(pendingFile, modalPassword.value.trim(), expireVal);
  });

// Copy buttons for recent list
document.querySelectorAll(".copy-btn").forEach((btn) =>
  btn.addEventListener("click", () => {
    const link = btn.dataset.copy;
    navigator.clipboard.writeText(link).then(() => {
      setStatus("Đã copy link", "success");
      showToast("Đã copy link");
    });
  })
);
