// =========================================================
// STATE MANAGEMENT & DOM ELEMENTS
// =========================================================
let currentUser = null;
let currentActivityData = null;
let currentMarkdown = "";
let currentFilter = "all";

// Elements
const authSection = document.getElementById("auth-section");
const dashboardSection = document.getElementById("dashboard-section");
const navUserArea = document.getElementById("nav-user-area");

const oauthStatusText = document.getElementById("oauth-status-text");
const btnGithubLogin = document.getElementById("btn-github-login");
const btnOauthSettings = document.getElementById("btn-oauth-settings");
const linkOpenOauthSetup = document.getElementById("link-open-oauth-setup");

const tabOauthBtn = document.getElementById("tab-oauth-btn");
const tabPatBtn = document.getElementById("tab-pat-btn");
const tabOauthContent = document.getElementById("tab-oauth-content");
const tabPatContent = document.getElementById("tab-pat-content");

const formPatLogin = document.getElementById("form-pat-login");
const inputPatToken = document.getElementById("input-pat-token");

const modalOAuthConfig = document.getElementById("modal-oauth-config");
const btnCloseModal = document.getElementById("btn-close-modal");
const btnCancelModal = document.getElementById("btn-cancel-modal");
const formSaveOAuth = document.getElementById("form-save-oauth");
const modalInputClientId = document.getElementById("modal-input-client-id");
const modalInputClientSecret = document.getElementById("modal-input-client-secret");
const setupHomeUrl = document.getElementById("setup-home-url");
const setupCallbackUrl = document.getElementById("setup-callback-url");

const inputDate = document.getElementById("input-date");
const selectTz = document.getElementById("select-tz");
const selectMode = document.getElementById("select-mode");
const btnCrawl = document.getElementById("btn-crawl");
const btnCrawlText = document.getElementById("btn-crawl-text");
const loadingSpinner = document.getElementById("loading-spinner");
const resultsContainer = document.getElementById("results-container");

const resultsHeadline = document.getElementById("results-headline");
const resultsMetaBadge = document.getElementById("results-meta-badge");
const timelineContainer = document.getElementById("timeline-container");
const markdownViewer = document.getElementById("markdown-viewer");
const markdownRaw = document.getElementById("markdown-raw");

const toast = document.getElementById("toast");

// =========================================================
// TOAST UTILITY
// =========================================================
function showToast(message, duration = 3000) {
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => {
    toast.classList.add("hidden");
  }, duration);
}

// =========================================================
// INITIALIZATION
// =========================================================
document.addEventListener("DOMContentLoaded", async () => {
  // 1. Cài đặt ngày mặc định là hôm nay
  const today = new Date().toISOString().split("T")[0];
  inputDate.value = today;

  // Cập nhật URL trong modal theo domain thực tế
  const origin = window.location.origin;
  setupHomeUrl.textContent = origin;
  setupCallbackUrl.textContent = `${origin}/callback`;

  // 2. Kiểm tra query params (nếu redirect từ callback)
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("auth") === "success") {
    showToast("🎉 Đăng nhập GitHub thành công!");
    window.history.replaceState({}, document.title, window.location.pathname);
  } else if (urlParams.get("auth_error")) {
    showToast(`⚠️ Lỗi đăng nhập: ${urlParams.get("auth_error")}`, 5000);
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  // 3. Tải cấu hình OAuth
  await checkOAuthConfig();

  // 4. Kiểm tra session đăng nhập hiện tại
  await checkAuthStatus();

  // 5. Setup event listeners
  setupEventListeners();
});

// =========================================================
// API CALLS & STATUS CHECKS
// =========================================================
async function checkOAuthConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    if (data.configured) {
      oauthStatusText.innerHTML = `✅ OAuth App đã sẵn sàng (Client ID: <code>${data.client_id.substring(0, 8)}...</code>). Bạn có thể đăng nhập ngay!`;
      btnGithubLogin.classList.remove("disabled");
      btnGithubLogin.setAttribute("href", "/login");
    } else {
      oauthStatusText.innerHTML = `⚠️ Chưa cấu hình GitHub OAuth App. Vui lòng bấm <b>Cấu hình ngay</b> hoặc dùng Personal Access Token.`;
      btnGithubLogin.onclick = (e) => {
        e.preventDefault();
        openOAuthModal();
      };
    }
  } catch (err) {
    oauthStatusText.textContent = "Không thể kiểm tra cấu hình OAuth.";
  }
}

async function checkAuthStatus() {
  try {
    const res = await fetch("/api/user");
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated && data.user) {
        currentUser = data.user;
        renderLoggedInUI();
        // Tự động crawl ngày hôm nay khi vừa vào
        crawlActivity();
        return;
      }
    }
    renderLoggedOutUI();
  } catch (err) {
    renderLoggedOutUI();
  }
}

function renderLoggedInUI() {
  authSection.classList.add("hidden");
  dashboardSection.classList.remove("hidden");

  // Render User Pill trên Navbar
  navUserArea.innerHTML = `
    <div class="user-pill">
      <img src="${currentUser.avatar_url}" alt="${currentUser.login}" class="user-avatar">
      <div class="user-details">
        <span class="user-name">${currentUser.name || currentUser.login}</span>
        <span class="user-login">@${currentUser.login}</span>
      </div>
    </div>
    <button id="btn-logout" class="btn btn-secondary btn-sm" title="Đăng xuất">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
        <polyline points="16 17 21 12 16 7"></polyline>
        <line x1="21" y1="12" x2="9" y2="12"></line>
      </svg>
      Đăng xuất
    </button>
  `;

  document.getElementById("btn-logout").onclick = handleLogout;
}

function renderLoggedOutUI() {
  authSection.classList.remove("hidden");
  dashboardSection.classList.add("hidden");
  navUserArea.innerHTML = `
    <button id="btn-oauth-settings" class="btn btn-secondary btn-sm">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3"></circle>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
      </svg>
      Cấu hình OAuth
    </button>
  `;
  document.getElementById("btn-oauth-settings").onclick = openOAuthModal;
}

async function handleLogout() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
    currentUser = null;
    showToast("Đã đăng xuất.");
    renderLoggedOutUI();
  } catch (err) {
    showToast("Lỗi khi đăng xuất.");
  }
}

// =========================================================
// EVENT LISTENERS & UI INTERACTIONS
// =========================================================
function setupEventListeners() {
  // Tabs Login Switcher
  tabOauthBtn.onclick = () => {
    tabOauthBtn.classList.add("active");
    tabPatBtn.classList.remove("active");
    tabOauthContent.classList.add("active");
    tabPatContent.classList.remove("active");
  };

  tabPatBtn.onclick = () => {
    tabPatBtn.classList.add("active");
    tabOauthBtn.classList.remove("active");
    tabPatContent.classList.add("active");
    tabOauthContent.classList.remove("active");
  };

  // PAT Login Form
  formPatLogin.onsubmit = async (e) => {
    e.preventDefault();
    const token = inputPatToken.value.trim();
    if (!token) return;

    const btnSubmit = document.getElementById("btn-submit-pat");
    btnSubmit.disabled = true;
    btnSubmit.textContent = "Đang xác thực...";

    try {
      const res = await fetch("/api/auth/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        showToast("🎉 Đăng nhập thành công!");
        currentUser = data.user;
        renderLoggedInUI();
        crawlActivity();
      } else {
        showToast(`❌ ${data.error || "Token không hợp lệ."}`, 4000);
      }
    } catch (err) {
      showToast("❌ Lỗi kết nối khi xác thực token.");
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.textContent = "Xác Thực & Đăng Nhập";
    }
  };

  // Modal OAuth Config Handlers
  if (linkOpenOauthSetup) linkOpenOauthSetup.onclick = openOAuthModal;
  if (btnCloseModal) btnCloseModal.onclick = closeOAuthModal;
  if (btnCancelModal) btnCancelModal.onclick = closeOAuthModal;

  modalOAuthConfig.onclick = (e) => {
    if (e.target === modalOAuthConfig) closeOAuthModal();
  };

  formSaveOAuth.onsubmit = async (e) => {
    e.preventDefault();
    const client_id = modalInputClientId.value.trim();
    const client_secret = modalInputClientSecret.value.trim();
    try {
      const res = await fetch("/api/config/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_id, client_secret })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        showToast("✅ Đã lưu cấu hình OAuth!");
        closeOAuthModal();
        await checkOAuthConfig();
      } else {
        showToast(`❌ ${data.error || "Không thể lưu."}`);
      }
    } catch (err) {
      showToast("❌ Lỗi lưu cấu hình.");
    }
  };

  // Quick Date Chips
  document.querySelectorAll(".chip-btn").forEach((chip) => {
    chip.onclick = () => {
      document.querySelectorAll(".chip-btn").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");

      const offsetDays = parseInt(chip.dataset.offset, 10);
      const target = new Date();
      target.setDate(target.getDate() - offsetDays);
      inputDate.value = target.toISOString().split("T")[0];

      crawlActivity();
    };
  });

  inputDate.onchange = () => {
    document.querySelectorAll(".chip-btn").forEach((c) => c.classList.remove("active"));
  };

  // Crawl Button
  btnCrawl.onclick = () => crawlActivity();

  // Export Buttons
  document.getElementById("btn-copy-markdown").onclick = copyMarkdownReport;
  document.getElementById("btn-copy-preview-md").onclick = copyMarkdownReport;
  document.getElementById("btn-download-json").onclick = downloadJson;
  document.getElementById("btn-download-md").onclick = downloadMarkdown;

  // Filter Tabs
  document.querySelectorAll(".activity-tab-btn").forEach((tab) => {
    tab.onclick = () => {
      document.querySelectorAll(".activity-tab-btn").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      currentFilter = tab.dataset.filter;
      renderTimelineView();
    };
  });
}

function openOAuthModal() {
  modalOAuthConfig.classList.remove("hidden");
}

function closeOAuthModal() {
  modalOAuthConfig.classList.add("hidden");
}

// =========================================================
// CRAWL ACTIVITY & RENDER RESULTS
// =========================================================
async function crawlActivity() {
  const dateVal = inputDate.value;
  if (!dateVal) {
    showToast("Vui lòng chọn ngày!");
    return;
  }

  btnCrawl.disabled = true;
  btnCrawlText.textContent = "Đang Tìm Kiếm...";
  loadingSpinner.classList.remove("hidden");
  resultsContainer.classList.add("hidden");

  try {
    const res = await fetch(`/api/activity?date=${dateVal}`);
    const jsonRes = await res.json();

    if (!res.ok || !jsonRes.success) {
      showToast(`❌ ${jsonRes.message || "Không thể lấy dữ liệu."}`, 4500);
      return;
    }

    currentActivityData = jsonRes.data;
    currentMarkdown = jsonRes.markdown;

    // Cập nhật kết quả lên UI
    updateResultsUI();
    showToast(`✅ Đã tìm thấy dữ liệu hoạt động ngày ${dateVal}!`);
  } catch (err) {
    showToast("❌ Lỗi mạng hoặc server khi crawl dữ liệu.");
  } finally {
    btnCrawl.disabled = false;
    btnCrawlText.textContent = "Tìm Kiếm Hoạt Động";
    loadingSpinner.classList.add("hidden");
  }
}

function updateResultsUI() {
  resultsContainer.classList.remove("hidden");
  resultsHeadline.textContent = `Hoạt Động Ngày: ${inputDate.value}`;
  resultsMetaBadge.textContent = "GitHub REST Search API";

  const cat = currentActivityData.categorized || {};

  const countCommits = (cat.commits || []).length;
  const countPrs = (cat.prs_created || []).length;
  const countIssues = (cat.issues_created || []).length;
  const countReviews = (cat.prs_reviewed || []).length;
  const countComments = (cat.items_commented || []).length;

  document.getElementById("stat-commits").textContent = countCommits;
  document.getElementById("stat-prs").textContent = countPrs;
  document.getElementById("stat-issues").textContent = countIssues;
  document.getElementById("stat-reviews").textContent = countReviews;
  document.getElementById("stat-comments").textContent = countComments;

  const totalAll = countCommits + countPrs + countIssues + countReviews + countComments;
  document.getElementById("count-all").textContent = totalAll;
  document.getElementById("count-commits").textContent = countCommits;
  document.getElementById("count-prs").textContent = countPrs;
  document.getElementById("count-issues").textContent = countIssues;
  document.getElementById("count-reviews").textContent = countReviews;
  document.getElementById("count-comments").textContent = countComments;

  markdownRaw.textContent = currentMarkdown;

  renderTimelineView();
}

function renderTimelineView() {
  if (currentFilter === "markdown") {
    timelineContainer.classList.add("hidden");
    markdownViewer.classList.remove("hidden");
    return;
  }

  timelineContainer.classList.remove("hidden");
  markdownViewer.classList.add("hidden");

  const cat = currentActivityData.categorized || {};
  let items = [];

  // 1. Commits
  if (currentFilter === "all" || currentFilter === "commits") {
    (cat.commits || []).forEach((c) => {
      items.push({
        type: "commit",
        badge: "Commit",
        badgeClass: "badge-commit",
        repo: c.repo,
        ref: "",
        title: c.message,
        url: c.url,
        sha: c.sha,
        time: formatTime(c.author_date)
      });
    });
  }

  // 2. Pull Requests Tạo Mới
  if (currentFilter === "all" || currentFilter === "prs") {
    (cat.prs_created || []).forEach((pr) => {
      items.push({
        type: "pr",
        badge: `PR [${pr.state}]`,
        badgeClass: "badge-pr",
        repo: pr.repo,
        ref: "",
        title: pr.title,
        url: pr.url,
        time: formatTime(pr.created_at)
      });
    });
  }

  // 3. Issues Tạo Mới
  if (currentFilter === "all" || currentFilter === "issues") {
    (cat.issues_created || []).forEach((iss) => {
      items.push({
        type: "issue",
        badge: `Issue [${iss.state}]`,
        badgeClass: "badge-issue",
        repo: iss.repo,
        ref: "",
        title: iss.title,
        url: iss.url,
        time: formatTime(iss.created_at)
      });
    });
  }

  // 4. PRs Đã Tham Gia Review
  if (currentFilter === "all" || currentFilter === "reviews") {
    (cat.prs_reviewed || []).forEach((r) => {
      items.push({
        type: "review",
        badge: "PR Review",
        badgeClass: "badge-review",
        repo: r.repo,
        ref: "",
        title: r.title,
        url: r.url,
        time: formatTime(r.updated_at)
      });
    });
  }

  // 5. Issues/PRs Có Thảo Luận / Bình Luận
  if (currentFilter === "all" || currentFilter === "comments") {
    (cat.items_commented || []).forEach((cm) => {
      items.push({
        type: "comment",
        badge: cm.type === "pull_request" ? "PR Comment" : "Issue Comment",
        badgeClass: "badge-comment",
        repo: cm.repo,
        ref: "",
        title: cm.title,
        url: cm.url,
        time: formatTime(cm.updated_at)
      });
    });
  }

  if (items.length === 0) {
    timelineContainer.innerHTML = `
      <div class="empty-state glass-panel">
        <div class="empty-icon">📭</div>
        <p>Không có hoạt động nào được ghi nhận cho mục này trong ngày ${inputDate.value}.</p>
      </div>
    `;
    return;
  }

  timelineContainer.innerHTML = items.map((it) => `
    <div class="timeline-item">
      <span class="item-badge ${it.badgeClass}">${it.badge}</span>
      <div class="item-main">
        <div class="item-header">
          <a href="https://github.com/${it.repo}" target="_blank" rel="noopener" class="item-repo">${it.repo}</a>
          ${it.ref ? `<span class="item-ref">${escapeHtml(it.ref)}</span>` : ""}
          <span class="item-time">${it.time}</span>
        </div>
        <div class="item-content">
          ${it.sha ? `<span class="item-sha">${it.sha}</span>` : ""}
          <a href="${it.url}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a>
        </div>
      </div>
    </div>
  `).join("");
}

function formatTime(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function escapeHtml(text) {
  if (!text) return "";
  const map = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  };
  return text.replace(/[&<>"']/g, (m) => map[m]);
}

// =========================================================
// EXPORTS & COPY
// =========================================================
function copyMarkdownReport() {
  if (!currentMarkdown) return;
  navigator.clipboard.writeText(currentMarkdown).then(() => {
    showToast("📋 Đã sao chép báo cáo Markdown vào Clipboard!");
  }).catch(() => {
    showToast("❌ Không thể sao chép tự động.");
  });
}

function downloadJson() {
  if (!currentActivityData) return;
  const blob = new Blob([JSON.stringify(currentActivityData, null, 2)], { type: "application/json" });
  downloadBlob(blob, `github_activity_${currentUser?.login}_${inputDate.value}.json`);
}

function downloadMarkdown() {
  if (!currentMarkdown) return;
  const blob = new Blob([currentMarkdown], { type: "text/markdown" });
  downloadBlob(blob, `github_activity_${currentUser?.login}_${inputDate.value}.md`);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(`💾 Đã tải xuống file: ${filename}`);
}
