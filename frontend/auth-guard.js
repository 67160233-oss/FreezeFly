// auth-guard.js - สคริปต์ตรวจสอบการล็อกอินก่อนเข้าใช้งานทุกหน้า
(function enforceAuth() {
    const currentPath = window.location.pathname.split('/').pop();
    const isAuthPage = currentPath === 'login.html' || currentPath === 'register.html';
    
    const userId = localStorage.getItem('user_id');
    const token = localStorage.getItem('access_token');
    const isLoggedIn = localStorage.getItem('isLoggedIn') === 'true';

    // ถ้ายังไม่ได้ล็อกอิน และไม่ได้อยู่ที่หน้า login/register ให้เด้งไปหน้า login.html ทันที
    if ((!userId || !token || !isLoggedIn) && !isAuthPage) {
        alert('🔒 คุณต้องเข้าสู่ระบบก่อนใช้งานฟีเจอร์นี้');
        window.location.href = 'login.html';
    }
})();

// ฟังก์ชันสำหรับ Navbar (แสดงชื่อผู้ใช้ + ปุ่ม Logout)
function setupNavbarAuth() {
    const userDisplay = localStorage.getItem('username') || localStorage.getItem('userEmail');
    const authArea = document.getElementById('authArea');

    if (authArea && userDisplay) {
        authArea.innerHTML = `
            <div class="flex items-center gap-3">
                <span class="text-xs font-medium text-slate-600 bg-slate-100 px-3 py-1.5 rounded-full border border-slate-200 flex items-center gap-1.5 shadow-xs">
                    <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    👤 ${userDisplay}
                </span>
                <button onclick="logout()" class="text-xs font-semibold text-red-500 hover:text-red-700 transition cursor-pointer px-3 py-1.5 rounded-lg hover:bg-red-50">
                    ออกจากระบบ
                </button>
            </div>
        `;
    }
}

// ฟังก์ชัน Logout สำหรับทุกหน้า
function logout() {
    localStorage.clear();
    alert('ออกจากระบบเรียบร้อยแล้ว');
    window.location.href = 'login.html';
}

document.addEventListener('DOMContentLoaded', setupNavbarAuth);