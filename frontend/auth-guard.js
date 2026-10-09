// auth-guard.js - โค้ดกลางที่ทุกหน้าใช้ร่วมกัน
// (ตั้งค่า API, ตรวจการล็อกอิน, แนบ Bearer token, ป้องกัน XSS, Navbar/Logout)
// ทุกหน้าต้องโหลดไฟล์นี้ก่อนสคริปต์ของหน้าตัวเอง

// เลือก backend อัตโนมัติ ไม่ต้องคอยแก้ URL เวลาสลับระหว่างเครื่องตัวเองกับ Render
// - เปิดจากเครื่องตัวเอง (localhost / 127.0.0.1 / ดับเบิลคลิกไฟล์) → ใช้ backend ในเครื่อง พอร์ต 8000
// - เปิดจากเว็บจริงบน Render → ใช้ backend บน Render
const IS_LOCAL = ['localhost', '127.0.0.1', ''].includes(window.location.hostname);
const API_BASE_URL = IS_LOCAL ? 'http://localhost:8000' : 'https://freezefly-backend.onrender.com';

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

// --------------------------------------------------------- booking modal
// โมดัลกรอกข้อมูลผู้โดยสาร + ใช้โค้ดส่วนลดแบบเห็นผลทันที ใช้แทน prompt()
// คืนค่า Promise: ได้ {passengerName, passengerEmail, promoCode} เมื่อกดยืนยัน, null เมื่อยกเลิก
function openBookingModal({
    title,
    flightLabel,
    basePrice,
    feePaid = 0,
    feeLabel = 'หักค่าธรรมเนียมที่จ่ายไว้',
    breakdown = [],   // [{label, value, tone}] แสดงที่มาของราคาตั๋ว เช่น ราคาตลาด / ส่วนต่างที่เราจ่ายให้
    flightId,
    defaultName = '',
    defaultEmail = '',
    confirmLabel = 'ยืนยัน'
}) {
    return new Promise((resolve) => {
        let settled = false;
        let appliedPromo = null; // { code, discount, title }

        const overlay = document.createElement('div');
        overlay.className = 'fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/50 backdrop-blur-sm px-4 py-8 overflow-y-auto';
        overlay.innerHTML = `
            <div class="bg-white w-full max-w-md rounded-2xl border border-slate-100 shadow-xl p-6 my-auto" role="dialog" aria-modal="true" aria-labelledby="bmTitle">
                <h2 id="bmTitle" class="text-lg font-bold text-slate-900">${escapeHtml(title)}</h2>
                <p class="text-xs text-slate-500 mt-1">${escapeHtml(flightLabel)}</p>

                <div class="mt-4 bg-slate-50 rounded-xl border border-slate-200 p-4 space-y-1.5 text-sm">
                    <div class="flex justify-between text-slate-600">
                        <span>ราคาตั๋ว</span>
                        <span>${baht(basePrice)}</span>
                    </div>
                    ${breakdown.map(b => `<div class="flex justify-between text-xs ${b.tone === 'good' ? 'text-emerald-700' : b.tone === 'warn' ? 'text-amber-700' : 'text-slate-400'}">
                        <span>${escapeHtml(b.label)}</span><span>${escapeHtml(b.value)}</span></div>`).join('')}
                    <div class="hidden">
                    </div>
                    <div class="flex justify-between text-slate-600 ${feePaid > 0 ? '' : 'hidden'}">
                        <span>${escapeHtml(feeLabel)}</span>
                        <span>-${baht(feePaid)}</span>
                    </div>
                    <div id="bmDiscountRow" class="flex justify-between text-emerald-700 hidden">
                        <span id="bmDiscountLabel">ส่วนลด</span>
                        <span id="bmDiscountValue">-฿0</span>
                    </div>
                    <div class="flex justify-between font-bold text-slate-900 pt-1.5 border-t border-slate-200 mt-1.5">
                        <span>ยอดที่ต้องชำระ</span>
                        <span id="bmFinalPrice">${baht(Math.max(0, basePrice - feePaid))}</span>
                    </div>
                </div>

                <div class="mt-4 space-y-3">
                    <div>
                        <label class="block text-xs font-medium text-slate-600 mb-1">ชื่อ-นามสกุลผู้โดยสาร</label>
                        <input id="bmName" type="text" placeholder="กรอกชื่อผู้โดยสาร" class="w-full text-sm border border-slate-200 rounded-xl px-4 py-2.5 focus:outline-none focus:border-emerald-500 transition">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-600 mb-1">อีเมลผู้โดยสาร</label>
                        <input id="bmEmail" type="email" placeholder="name@example.com" class="w-full text-sm border border-slate-200 rounded-xl px-4 py-2.5 focus:outline-none focus:border-emerald-500 transition">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-600 mb-1">โค้ดส่วนลด (ถ้ามี)</label>
                        <div class="flex gap-2">
                            <input id="bmPromo" type="text" placeholder="เช่น NEWUSER2026" class="flex-1 text-sm border border-slate-200 rounded-xl px-4 py-2.5 focus:outline-none focus:border-emerald-500 transition uppercase">
                            <button id="bmPromoApply" type="button" class="bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold px-4 rounded-xl transition cursor-pointer shrink-0">ใช้โค้ด</button>
                        </div>
                        <p id="bmPromoMsg" class="text-xs mt-1.5 hidden"></p>
                    </div>
                </div>

                <div class="flex gap-3 mt-6">
                    <button id="bmCancel" type="button" class="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold py-2.5 rounded-xl transition cursor-pointer">ยกเลิก</button>
                    <button id="bmConfirm" type="button" disabled class="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold py-2.5 rounded-xl transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed">${escapeHtml(confirmLabel)}</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';

        const nameInput = overlay.querySelector('#bmName');
        const emailInput = overlay.querySelector('#bmEmail');
        const promoInput = overlay.querySelector('#bmPromo');
        const promoMsg = overlay.querySelector('#bmPromoMsg');
        const promoApplyBtn = overlay.querySelector('#bmPromoApply');
        const confirmBtn = overlay.querySelector('#bmConfirm');
        const cancelBtn = overlay.querySelector('#bmCancel');
        const discountRow = overlay.querySelector('#bmDiscountRow');
        const discountLabel = overlay.querySelector('#bmDiscountLabel');
        const discountValue = overlay.querySelector('#bmDiscountValue');
        const finalPriceEl = overlay.querySelector('#bmFinalPrice');

        nameInput.value = defaultName;
        emailInput.value = defaultEmail;

        function updateFinalPrice() {
            const discount = appliedPromo ? appliedPromo.discount : 0;
            finalPriceEl.textContent = baht(Math.max(0, basePrice - feePaid - discount));
        }

        function validateForm() {
            confirmBtn.disabled = !(nameInput.value.trim() && emailInput.value.trim());
        }
        nameInput.addEventListener('input', validateForm);
        emailInput.addEventListener('input', validateForm);
        validateForm();

        function showPromoMsg(text, ok) {
            promoMsg.textContent = text;
            promoMsg.className = `text-xs mt-1.5 ${ok ? 'text-emerald-600' : 'text-red-500'}`;
        }

        async function applyPromo() {
            const code = promoInput.value.trim();
            if (!code) {
                appliedPromo = null;
                discountRow.classList.add('hidden');
                promoMsg.classList.add('hidden');
                updateFinalPrice();
                return;
            }
            promoApplyBtn.disabled = true;
            promoApplyBtn.textContent = 'กำลังตรวจ...';
            try {
                const res = await apiFetch('/promotions/validate', {
                    method: 'POST',
                    body: JSON.stringify({ code, price: basePrice, flight_id: flightId })
                });
                if (res.status === 401) return; // apiFetch พากลับหน้า login ให้แล้ว
                const data = await res.json();
                if (res.ok) {
                    appliedPromo = { code: data.code, discount: data.discount_amount, title: data.title };
                    discountLabel.textContent = `ส่วนลด (${data.title})`;
                    discountValue.textContent = `-${baht(data.discount_amount)}`;
                    discountRow.classList.remove('hidden');
                    showPromoMsg(`✅ ใช้โค้ด ${data.code} สำเร็จ`, true);
                } else {
                    appliedPromo = null;
                    discountRow.classList.add('hidden');
                    showPromoMsg(`❌ ${getErrorMessage(data, 'โค้ดส่วนลดไม่ถูกต้อง')}`, false);
                }
            } catch (err) {
                appliedPromo = null;
                discountRow.classList.add('hidden');
                showPromoMsg('ไม่สามารถตรวจสอบโค้ดได้ ลองใหม่อีกครั้ง', false);
            } finally {
                promoMsg.classList.remove('hidden');
                promoApplyBtn.disabled = false;
                promoApplyBtn.textContent = 'ใช้โค้ด';
                updateFinalPrice();
            }
        }
        promoApplyBtn.addEventListener('click', applyPromo);
        promoInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); applyPromo(); }
        });

        function close(result) {
            if (settled) return;
            settled = true;
            document.removeEventListener('keydown', onKeydown);
            document.body.style.overflow = '';
            overlay.remove();
            resolve(result);
        }
        function onKeydown(e) {
            if (e.key === 'Escape') close(null);
        }
        document.addEventListener('keydown', onKeydown);

        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(null); });
        cancelBtn.addEventListener('click', () => close(null));
        confirmBtn.addEventListener('click', () => close({
            passengerName: nameInput.value.trim(),
            passengerEmail: emailInput.value.trim(),
            promoCode: appliedPromo ? appliedPromo.code : null
        }));

        nameInput.focus();
    });
}

// ------------------------------------------------------ AI price advice
function adviceStyle(level) {
    return {
        rising: 'bg-amber-50 text-amber-800 border border-amber-200',
        uncertain: 'bg-sky-50 text-sky-800 border border-sky-200',
        stable: 'bg-emerald-50 text-emerald-800 border border-emerald-200',
        buy_now: 'bg-slate-100 text-slate-700 border border-slate-200',
    }[level] || 'bg-slate-100 text-slate-700 border border-slate-200';
}

// ------------------------------------------------------ freeze duration modal
function fmtDateTime(value) {
    return new Date(value).toLocaleString('th-TH', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

// ให้ลูกค้าเลือกระยะตรึงราคา (ตัวเลือกและกฎมาจาก backend: flight.freeze_options)
// คืนค่า Promise: ได้จำนวนชั่วโมงที่เลือก หรือ null ถ้ายกเลิก
function openFreezeModal(flight) {
    return new Promise((resolve) => {
        let settled = false;
        const options = flight.freeze_options || [];
        let selected = (options.find(o => o.available) || {}).hours ?? null;

        const overlay = document.createElement('div');
        overlay.className = 'fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/50 backdrop-blur-sm px-4 py-8 overflow-y-auto';
        overlay.innerHTML = `
            <div class="bg-white w-full max-w-md rounded-2xl border border-slate-100 shadow-xl p-6 my-auto" role="dialog" aria-modal="true" aria-labelledby="fmTitle">
                <h2 id="fmTitle" class="text-lg font-bold text-slate-900">เลือกระยะเวลาตรึงราคา</h2>
                <p class="text-xs text-slate-500 mt-1">${escapeHtml(flight.origin)} ➔ ${escapeHtml(flight.destination)} · เที่ยวบิน #${escapeHtml(flight.flight_number)} · ราคาที่จะล็อก ${baht(flight.price)} (ราคาวันนี้)</p>
                ${flight.price_advice ? `<p class="text-xs mt-2 px-3 py-2 rounded-lg ${adviceStyle(flight.price_advice.level)}">🤖 ${escapeHtml(flight.price_advice.message)}</p>` : ''}
                <div id="fmOptions" class="mt-4 space-y-2" role="radiogroup"></div>
                <div class="mt-4 bg-slate-50 rounded-xl border border-slate-200 p-3 text-xs text-slate-600 leading-relaxed space-y-1">
                    <p>✈️ เครื่องออก ${fmtDateTime(flight.departure_time)} · ปิดขายตั๋ว ${fmtDateTime(flight.booking_closes_at)}</p>
                    <p>🤖 ค่าธรรมเนียมคิดตามความเสี่ยงที่ AI ประเมิน: เส้นทางที่ราคานิ่งจ่ายถูก ตรึงนานหรือใกล้วันบินจ่ายแพงขึ้น</p>
                    <p>🛡️ ราคาขึ้น เราจ่ายส่วนต่างให้สูงสุด <b class="text-slate-800">${baht((options[0] || {}).coverage_cap_amount || 0)}</b> (20% ของราคาที่ล็อก) · ราคาลง คุณได้ราคาใหม่ที่ถูกกว่า</p>
                    <p>💳 ค่าธรรมเนียมใช้จ่ายส่วนต่างก่อน ส่วนที่เหลือ<b class="text-slate-800">หักเป็นค่าตั๋ว</b> คุณจึงไม่จ่ายแพงกว่าราคาตลาด</p>
                    <p>⏱️ ถ้าไม่ออกตั๋วภายในเวลาที่เลือก สิทธิ์หมดอายุและไม่คืนค่าธรรมเนียม (ยกเว้นที่นั่งเต็ม หรือราคาขึ้นเกินเพดาน)</p>
                </div>
                <div class="flex gap-3 mt-6">
                    <button id="fmCancel" type="button" class="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold py-2.5 rounded-xl transition cursor-pointer">ยกเลิก</button>
                    <button id="fmConfirm" type="button" class="flex-1 bg-cyan-600 hover:bg-cyan-700 text-white text-sm font-semibold py-2.5 rounded-xl transition cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"></button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';

        const listEl = overlay.querySelector('#fmOptions');
        const confirmBtn = overlay.querySelector('#fmConfirm');

        function renderOptions() {
            listEl.innerHTML = options.map(o => {
                const isSel = o.hours === selected;
                const base = 'w-full text-left rounded-xl border px-4 py-3 transition flex items-center justify-between gap-3';
                const cls = !o.available ? 'border-slate-200 bg-slate-50 opacity-60 cursor-not-allowed'
                    : isSel ? 'border-cyan-500 bg-cyan-50 ring-2 ring-cyan-200 cursor-pointer'
                    : 'border-slate-200 hover:border-cyan-300 cursor-pointer';
                const sub = o.available
                    ? `สิทธิ์อยู่ถึง ${fmtDateTime(o.expires_at)}`
                    : escapeHtml(o.reason || 'เลือกไม่ได้');
                return `
                    <button type="button" role="radio" aria-checked="${isSel}" data-hours="${Number(o.hours)}" ${o.available ? '' : 'disabled'} class="${base} ${cls}">
                        <span>
                            <span class="block text-sm font-semibold text-slate-900">${escapeHtml(o.label)}</span>
                            <span class="block text-xs ${o.available ? 'text-slate-500' : 'text-red-500'} mt-0.5">${sub}</span>
                            ${o.available && o.rise_probability != null ? `<span class="block text-[11px] text-slate-400 mt-0.5">🤖 โอกาสราคาขึ้นในช่วงนี้ ${Math.round(o.rise_probability * 100)}%</span>` : ''}
                        </span>
                        <span class="text-right shrink-0">
                            <span class="block text-sm font-bold text-cyan-700">${baht(o.fee_amount)}</span>
                            <span class="block text-[11px] text-slate-400">${o.available ? (o.fee_rate * 100).toFixed(1) + '% ของราคาตั๋ว' : ''}</span>
                        </span>
                    </button>`;
            }).join('');
            const opt = options.find(o => o.hours === selected);
            confirmBtn.disabled = !opt;
            confirmBtn.textContent = opt ? `ตรึงราคา ${opt.label} · ${baht(opt.fee_amount)}` : 'ไม่มีระยะที่เลือกได้';
        }
        listEl.addEventListener('click', (e) => {
            const btn = e.target.closest('button[data-hours]');
            if (!btn || btn.disabled) return;
            selected = Number(btn.dataset.hours);
            renderOptions();
        });
        renderOptions();

        function close(result) {
            if (settled) return;
            settled = true;
            document.removeEventListener('keydown', onKeydown);
            document.body.style.overflow = '';
            overlay.remove();
            resolve(result);
        }
        function onKeydown(e) { if (e.key === 'Escape') close(null); }
        document.addEventListener('keydown', onKeydown);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(null); });
        overlay.querySelector('#fmCancel').addEventListener('click', () => close(null));
        confirmBtn.addEventListener('click', () => close(selected));
    });
}

// ---------------------------------------------------- confirm / message modal
// แทนที่ confirm() ของเบราว์เซอร์ คืนค่า Promise<boolean>
function openConfirmModal({ title, message, confirmLabel = 'ยืนยัน', cancelLabel = 'ยกเลิก', tone = 'default' }) {
    return new Promise((resolve) => {
        let settled = false;
        const confirmBtnClass = tone === 'danger' ? 'bg-red-600 hover:bg-red-700' : 'bg-emerald-600 hover:bg-emerald-700';

        const overlay = document.createElement('div');
        overlay.className = 'fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/50 backdrop-blur-sm px-4';
        overlay.innerHTML = `
            <div class="bg-white w-full max-w-sm rounded-2xl border border-slate-100 shadow-xl p-6" role="dialog" aria-modal="true" aria-labelledby="cmTitle">
                <h2 id="cmTitle" class="text-lg font-bold text-slate-900">${escapeHtml(title)}</h2>
                <p class="text-sm text-slate-500 mt-2 leading-relaxed whitespace-pre-line">${escapeHtml(message)}</p>
                <div class="flex gap-3 mt-6">
                    <button id="cmCancel" type="button" class="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold py-2.5 rounded-xl transition cursor-pointer">${escapeHtml(cancelLabel)}</button>
                    <button id="cmConfirm" type="button" class="flex-1 ${confirmBtnClass} text-white text-sm font-semibold py-2.5 rounded-xl transition cursor-pointer">${escapeHtml(confirmLabel)}</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';

        function close(result) {
            if (settled) return;
            settled = true;
            document.removeEventListener('keydown', onKeydown);
            document.body.style.overflow = '';
            overlay.remove();
            resolve(result);
        }
        function onKeydown(e) { if (e.key === 'Escape') close(false); }
        document.addEventListener('keydown', onKeydown);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });
        overlay.querySelector('#cmCancel').addEventListener('click', () => close(false));
        overlay.querySelector('#cmConfirm').addEventListener('click', () => close(true));
        overlay.querySelector('#cmConfirm').focus();
    });
}

// แทนที่ alert() ของเบราว์เซอร์ คืนค่า Promise<void> ที่ resolve เมื่อผู้ใช้กด "ตกลง"
function openMessageModal({ title, message, tone = 'success' }) {
    return new Promise((resolve) => {
        let settled = false;
        const icon = tone === 'error' ? '❌' : tone === 'info' ? 'ℹ️' : '✅';
        const titleColor = tone === 'error' ? 'text-red-600' : 'text-emerald-600';

        const overlay = document.createElement('div');
        overlay.className = 'fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/50 backdrop-blur-sm px-4';
        overlay.innerHTML = `
            <div class="bg-white w-full max-w-sm rounded-2xl border border-slate-100 shadow-xl p-6 text-center" role="dialog" aria-modal="true" aria-labelledby="mmTitle">
                <div class="text-3xl mb-2">${icon}</div>
                <h2 id="mmTitle" class="text-lg font-bold ${titleColor}">${escapeHtml(title)}</h2>
                <p class="text-sm text-slate-500 mt-2 leading-relaxed whitespace-pre-line">${escapeHtml(message)}</p>
                <button id="mmOk" type="button" class="mt-6 w-full bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold py-2.5 rounded-xl transition cursor-pointer">ตกลง</button>
            </div>
        `;
        document.body.appendChild(overlay);
        document.body.style.overflow = 'hidden';

        function close() {
            if (settled) return;
            settled = true;
            document.removeEventListener('keydown', onKeydown);
            document.body.style.overflow = '';
            overlay.remove();
            resolve();
        }
        function onKeydown(e) { if (e.key === 'Escape' || e.key === 'Enter') close(); }
        document.addEventListener('keydown', onKeydown);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
        overlay.querySelector('#mmOk').addEventListener('click', close);
        overlay.querySelector('#mmOk').focus();
    });
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