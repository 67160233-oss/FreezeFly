// auth-guard.js - โค้ดกลางที่ทุกหน้าใช้ร่วมกัน
// (ตั้งค่า API, ตรวจการล็อกอิน, แนบ Bearer token, ป้องกัน XSS, Navbar/Logout)
// ทุกหน้าต้องโหลดไฟล์นี้ก่อนสคริปต์ของหน้าตัวเอง

const API_BASE_URL = 'http://localhost:8000';

// ---------------------------------------------------------------- session
function isAuthPage() {
    const page = window.location.pathname.split('/').pop();
    return page === 'login.html' || page === 'register.html';
}

function isLoggedIn() {
    return Boolean(
        localStorage.getItem('user_id') &&
        localStorage.getItem('access_token') &&
        localStorage.getItem('isLoggedIn') === 'true'
    );
}

function getUserId() {
    return localStorage.getItem('user_id');
}

// ถ้ายังไม่ได้ล็อกอิน และไม่ได้อยู่ที่หน้า login/register ให้เด้งไปหน้า login.html ทันที
(function enforceAuth() {
    if (!isLoggedIn() && !isAuthPage()) {
        alert('🔒 คุณต้องเข้าสู่ระบบก่อนใช้งานฟีเจอร์นี้');
        window.location.href = 'login.html';
    }
})();

let sessionExpiredHandled = false;
function handleSessionExpired() {
    if (sessionExpiredHandled) return; // หลาย request พร้อมกันให้แจ้งครั้งเดียว
    sessionExpiredHandled = true;
    localStorage.clear();
    alert('เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่อีกครั้ง');
    window.location.href = 'login.html';
}

// ------------------------------------------------------------------- API
// เรียก API พร้อมแนบ Authorization: Bearer <token> ให้อัตโนมัติ
// ถ้า token หมดอายุ/ใช้ไม่ได้ (401) จะพากลับไปหน้า login
// ผู้เรียกควรตรวจ `if (res.status === 401) return;` หลังเรียก
async function apiFetch(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = localStorage.getItem('access_token');
    if (token) headers.set('Authorization', `Bearer ${token}`);
    if (options.body && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }

    const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
    if (res.status === 401 && !isAuthPage()) handleSessionExpired();
    return res;
}

// ดึงข้อความ error จาก response ของ FastAPI (รองรับทั้ง detail แบบข้อความและแบบ list ของ 422)
function getErrorMessage(data, fallback) {
    if (!data || !data.detail) return fallback;
    if (Array.isArray(data.detail)) return data.detail.map(e => e.msg).join(', ');
    return String(data.detail);
}

async function readError(res, fallback) {
    try {
        return getErrorMessage(await res.json(), fallback);
    } catch (e) {
        return fallback;
    }
}

// ------------------------------------------------------------- utilities
// ป้องกัน XSS: ต้องใช้ครอบข้อมูลจากผู้ใช้/เซิร์ฟเวอร์ทุกตัวที่ใส่ลงใน innerHTML
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[ch]));
}

function baht(amount) {
    return `฿${Number(amount || 0).toLocaleString()}`;
}

// ---------------------------------------------------------------- navbar
// แสดงชื่อผู้ใช้ + ปุ่ม Logout
function setupNavbarAuth() {
    const userDisplay = localStorage.getItem('username') || localStorage.getItem('userEmail');
    const authArea = document.getElementById('authArea');

    if (authArea && userDisplay && isLoggedIn()) {
        authArea.innerHTML = `
            <div class="flex items-center gap-3">
                <span class="text-xs font-medium text-slate-600 bg-slate-100 px-3 py-1.5 rounded-full border border-slate-200 flex items-center gap-1.5 shadow-xs">
                    <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    👤 ${escapeHtml(userDisplay)}
                </span>
                <button id="logoutBtn" class="text-xs font-semibold text-red-500 hover:text-red-700 transition cursor-pointer px-3 py-1.5 rounded-lg hover:bg-red-50">
                    ออกจากระบบ
                </button>
            </div>
        `;
        document.getElementById('logoutBtn').addEventListener('click', logout);
    }
}

function logout() {
    localStorage.clear();
    alert('ออกจากระบบเรียบร้อยแล้ว');
    window.location.href = 'login.html';
}

document.addEventListener('DOMContentLoaded', setupNavbarAuth);