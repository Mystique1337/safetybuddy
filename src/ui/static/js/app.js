/* ═══════════════════════════════════════════
   SafetyBuddy Core JavaScript
   ═══════════════════════════════════════════ */

// ── Sidebar Toggle (mobile) ──────────────
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('show');
}

// Close sidebar on outside click (mobile)
document.addEventListener('click', (e) => {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.querySelector('.sidebar-toggle');
    if (sidebar && sidebar.classList.contains('show') &&
        !sidebar.contains(e.target) && !toggle.contains(e.target)) {
        sidebar.classList.remove('show');
    }
});

// ── Clock ────────────────────────────────
function updateClock() {
    const el = document.getElementById('clock');
    if (el) {
        el.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
}
updateClock();
setInterval(updateClock, 30000);

// ── API Health Check ─────────────────────
async function checkHealth() {
    const statusEl = document.querySelector('#apiStatus');
    if (!statusEl) return;

    try {
        const res = await fetch('/api/health');
        const data = await res.json();
        const dot = statusEl.querySelector('.status-dot');
        const label = statusEl.querySelector('small');

        if (data.status === 'healthy') {
            dot.className = 'status-dot online';
            label.textContent = data.llm_endpoint_configured ? 'System online' : 'System offline';
        } else {
            dot.className = 'status-dot offline';
            label.textContent = 'API Error';
        }
    } catch (e) {
        const dot = statusEl.querySelector('.status-dot');
        const label = statusEl.querySelector('small');
        dot.className = 'status-dot offline';
        label.textContent = 'Disconnected';
    }
}
checkHealth();
setInterval(checkHealth, 60000);

// ── Alert Badge ──────────────────────────
async function updateAlertBadge() {
    try {
        const res = await fetch('/api/alerts');
        const data = await res.json();
        const badge = document.getElementById('alertBadge');
        const count = document.getElementById('alertCount');
        if (badge && count && data.alerts && data.alerts.length > 0) {
            badge.style.display = 'inline-block';
            count.textContent = data.alerts.length;
        }
    } catch (e) { /* silent */ }
}
updateAlertBadge();
setInterval(updateAlertBadge, 30000);

// ── Toast Notifications ──────────────────
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const iconMap = {
        info: 'bi-info-circle',
        success: 'bi-check-circle',
        warning: 'bi-exclamation-triangle',
        danger: 'bi-x-circle',
    };

    const id = 'toast-' + Date.now();
    const html = `
        <div id="${id}" class="toast align-items-center text-bg-${type} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="bi ${iconMap[type] || 'bi-info-circle'} me-2"></i>${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);

    const toastEl = document.getElementById(id);
    const toast = new bootstrap.Toast(toastEl, { autohide: true, delay: 5000 });
    toast.show();

    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

// ── Optional product-updates capture ─────
function showSubscribe() {
    if (localStorage.getItem('sb_sub')) return;   // already dismissed or subscribed
    const card = document.getElementById('subscribeCard');
    if (!card) return;
    setTimeout(() => { card.style.display = 'flex'; requestAnimationFrame(() => card.classList.add('show')); }, 9000);
}

function dismissSubscribe() {
    const card = document.getElementById('subscribeCard');
    localStorage.setItem('sb_sub', 'dismissed');
    if (card) { card.classList.remove('show'); setTimeout(() => { card.style.display = 'none'; }, 250); }
}

async function submitSubscribe(e) {
    e.preventDefault();
    const email = document.getElementById('subscribeEmail').value.trim();
    const btn = document.getElementById('subscribeBtn');
    const msg = document.getElementById('subscribeMsg');
    btn.disabled = true;
    try {
        const res = await fetch('/api/subscribe', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, source: 'footer' }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Something went wrong');
        msg.innerHTML = '<span class="text-success"><i class="bi bi-check-circle"></i> Thanks, you are on the list.</span>';
        localStorage.setItem('sb_sub', 'done');
        setTimeout(dismissSubscribe, 2200);
    } catch (err) {
        msg.innerHTML = '<span class="text-danger">' + err.message + '</span>';
        btn.disabled = false;
    }
    return false;
}

showSubscribe();
