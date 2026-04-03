/**
 * app.js — Social Agent UI
 *
 * Chạy trong 2 môi trường:
 *   1. pywebview (desktop): gọi window.pywebview.api.<method>()
 *   2. Browser / web: gọi fetch('/api/<endpoint>')
 *
 * Tất cả calls đi qua api() helper bên dưới — không cần sửa UI code khi đổi môi trường.
 */

// ─── API Bridge ─────────────────────────────────────────────────────────────

const isDesktop = () => typeof window.pywebview !== "undefined";

/**
 * Gọi Python backend.
 * Desktop: window.pywebview.api[method](...args)
 * Web:     POST /api/<method> với args là body JSON
 */
async function api(method, args = {}) {
  if (isDesktop()) {
    return await window.pywebview.api[method](args);
  }
  const res = await fetch(`/api/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// ─── Navigation ──────────────────────────────────────────────────────────────

document.querySelectorAll(".sidebar li").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".sidebar li").forEach((i) => i.classList.remove("active"));
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    item.classList.add("active");
    const page = document.getElementById(`page-${item.dataset.page}`);
    if (page) page.classList.add("active");
  });
});

// ─── Init ────────────────────────────────────────────────────────────────────

async function init() {
  try {
    const stats = await api("get_stats");
    document.querySelector("#page-dashboard .placeholder").textContent =
      `Tổng bài đã đăng: ${stats.total ?? 0}`;
  } catch (e) {
    document.querySelector("#page-dashboard .placeholder").textContent =
      "Không thể kết nối với backend.";
  }
}

document.addEventListener("DOMContentLoaded", init);
