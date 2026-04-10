document.addEventListener('DOMContentLoaded', () => {
    // ══════════════════════════════════════
    //  ELEMENTS
    // ══════════════════════════════════════
    const nav = document.getElementById('main-nav');
    const navLinks = document.querySelectorAll('.nav-links a');
    const pages = {
        setup: document.getElementById('page-setup'),
        dashboard: document.getElementById('page-dashboard'),
        detail: document.getElementById('page-detail'),
        settings: document.getElementById('page-settings')
    };

    let ws = null;
    let machines = {};   // client_id -> machine data
    let currentDetail = null; // client_id of detail view
    let logsAuthenticated = false;
    let shellAuthenticated = false;
    let logsAutoScroll = true;
    let cachedPassword = null;

    // ══════════════════════════════════════
    //  CANVAS BACKGROUND
    // ══════════════════════════════════════
    const canvas = document.getElementById('bg-canvas');
    const ctx = canvas.getContext('2d');
    let cW, cH, particles = [];
    const pConfig = {
        color1: '#8c52ff', color2: '#ff914d',
        amount: 70, variantSpeed: 0.8, linkRadius: 150, mouseRadius: 160
    };
    let mouse = { x: -1000, y: -1000 };

    function resizeCanvas() { cW = canvas.width = window.innerWidth; cH = canvas.height = window.innerHeight; }
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
    window.addEventListener('touchmove', e => { mouse.x = e.touches[0].clientX; mouse.y = e.touches[0].clientY; });

    class Particle {
        constructor() {
            this.x = Math.random() * cW; this.y = Math.random() * cH;
            this.vx = (Math.random() - 0.5) * pConfig.variantSpeed;
            this.vy = (Math.random() - 0.5) * pConfig.variantSpeed;
            this.size = Math.random() * 2 + 1;
            this.color = Math.random() > 0.5 ? pConfig.color1 : pConfig.color2;
        }
        update() {
            this.x += this.vx; this.y += this.vy;
            if (this.x < 0 || this.x > cW) this.vx *= -1;
            if (this.y < 0 || this.y > cH) this.vy *= -1;
            const dx = mouse.x - this.x, dy = mouse.y - this.y;
            const d = Math.sqrt(dx * dx + dy * dy);
            if (d < pConfig.mouseRadius) {
                const f = (pConfig.mouseRadius - d) / pConfig.mouseRadius;
                this.x -= (dx / d) * f * 6; this.y -= (dy / d) * f * 6;
            }
        }
        draw() {
            ctx.beginPath(); ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fillStyle = this.color; ctx.fill();
        }
    }

    function initParticles() {
        particles = [];
        const n = window.innerWidth < 768 ? pConfig.amount / 2 : pConfig.amount;
        for (let i = 0; i < n; i++) particles.push(new Particle());
    }

    function animateCanvas() {
        ctx.clearRect(0, 0, cW, cH);
        particles.forEach(p => { p.update(); p.draw(); });
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x, dy = particles[i].y - particles[j].y;
                const d = Math.sqrt(dx * dx + dy * dy);
                if (d < pConfig.linkRadius) {
                    ctx.beginPath();
                    ctx.strokeStyle = `rgba(255,255,255,${(1 - d / pConfig.linkRadius) * 0.12})`;
                    ctx.lineWidth = 1;
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.stroke();
                }
            }
        }
        requestAnimationFrame(animateCanvas);
    }
    initParticles(); animateCanvas();

    // ══════════════════════════════════════
    //  NAVIGATION
    // ══════════════════════════════════════
    function showPage(name) {
        Object.values(pages).forEach(p => p.classList.add('hidden'));
        Object.values(pages).forEach(p => p.classList.remove('active'));
        const p = pages[name];
        if (p) { p.classList.remove('hidden'); p.classList.add('active'); }
        navLinks.forEach(l => l.classList.toggle('active', l.dataset.page === name));
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    navLinks.forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            const pg = link.dataset.page;
            if (pg === 'settings') loadSettings();
            showPage(pg);
        });
    });

    window.addEventListener('scroll', () => {
        nav.classList.toggle('scrolled', window.scrollY > 50);
    });

    // ══════════════════════════════════════
    //  INIT — check setup status
    // ══════════════════════════════════════
    async function init() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            if (!data.setup_done) {
                showPage('setup');
                pages.setup.classList.add('active');
            } else {
                nav.classList.remove('hidden');
                showPage('dashboard');
                connectWebSocket();
            }
        } catch (e) {
            console.error('Init failed:', e);
        }
    }

    // ══════════════════════════════════════
    //  SETUP
    // ══════════════════════════════════════
    document.getElementById('setup-btn').addEventListener('click', async () => {
        const pw1 = document.getElementById('setup-pw1').value;
        const pw2 = document.getElementById('setup-pw2').value;
        const err = document.getElementById('setup-error');
        err.textContent = '';

        if (pw1.length < 4) { err.textContent = 'Passwort zu kurz (min. 4 Zeichen)'; return; }
        if (pw1 !== pw2) { err.textContent = 'Passwörter stimmen nicht überein'; return; }

        try {
            const res = await fetch('/api/setup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: pw1 })
            });
            const data = await res.json();
            if (data.api_key) {
                document.getElementById('setup-form').classList.add('hidden');
                document.getElementById('setup-complete').classList.remove('hidden');
                document.getElementById('setup-key-display').textContent = data.api_key;
            } else {
                err.textContent = data.detail || 'Fehler beim Setup';
            }
        } catch (e) {
            err.textContent = 'Verbindungsfehler';
        }
    });

    document.getElementById('setup-done-btn').addEventListener('click', () => {
        nav.classList.remove('hidden');
        showPage('dashboard');
        connectWebSocket();
    });

    // ══════════════════════════════════════
    //  WEBSOCKET
    // ══════════════════════════════════════
    function connectWebSocket() {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${proto}//${location.host}/ws/frontend`);

        ws.onopen = () => console.log('WS connected');

        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            handleWSMessage(msg);
        };

        ws.onclose = () => {
            console.log('WS closed, reconnecting in 3s...');
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = () => ws.close();
    }

    function handleWSMessage(msg) {
        switch (msg.type) {
            case 'init':
                machines = {};
                (msg.machines || []).forEach(m => { machines[m.client_id] = m; });
                renderDashboard();
                break;

            case 'telemetry':
                const cid = msg.client_id;
                if (!machines[cid]) machines[cid] = {};
                machines[cid] = { ...machines[cid], ...msg.data, online: true, live: msg.data };
                renderDashboard();
                if (currentDetail === cid) updateDetailLive(msg.data);
                break;

            case 'client_online':
                if (!machines[msg.client_id]) machines[msg.client_id] = {};
                machines[msg.client_id].online = true;
                machines[msg.client_id].client_name = msg.client_name;
                machines[msg.client_id].client_id = msg.client_id;
                renderDashboard();
                break;

            case 'client_offline':
                if (machines[msg.client_id]) machines[msg.client_id].online = false;
                renderDashboard();
                if (currentDetail === msg.client_id) updateDetailStatus(false);
                break;

            case 'processes':
                if (currentDetail === msg.client_id) renderProcesses(msg.data);
                break;

            case 'services':
                if (currentDetail === msg.client_id) renderServices(msg.data);
                break;

            case 'updates':
                if (currentDetail === msg.client_id) renderUpdates(msg.data);
                break;

            case 'smart':
                if (currentDetail === msg.client_id) renderSmart(msg.data);
                break;

            case 'logs_line':
                if (currentDetail === msg.client_id) appendLog(msg.data);
                break;

            case 'shell_output':
                if (currentDetail === msg.client_id) appendShell(msg.data);
                break;

            case 'action_result':
                // Could show a toast/notification
                break;
        }
    }

    // ══════════════════════════════════════
    //  DASHBOARD
    // ══════════════════════════════════════
    const dashboardGrid = document.getElementById('dashboard-grid');
    const dashboardEmpty = document.getElementById('dashboard-empty');

    // ── Drag & Drop order persistence ──
    let cardOrder = JSON.parse(localStorage.getItem('m-observe-card-order') || '[]');
    let dragSrcId = null;

    function saveCardOrder() {
        const order = [];
        dashboardGrid.querySelectorAll('.machine-card').forEach(c => {
            if (c.dataset.clientId) order.push(c.dataset.clientId);
        });
        cardOrder = order;
        localStorage.setItem('m-observe-card-order', JSON.stringify(order));
    }

    function renderDashboard() {
        const ids = Object.keys(machines);
        if (ids.length === 0) {
            dashboardGrid.classList.add('hidden');
            dashboardEmpty.classList.remove('hidden');
            return;
        }
        dashboardGrid.classList.remove('hidden');
        dashboardEmpty.classList.add('hidden');

        // Sort: use saved order first, then online first, then alpha for new ones
        const orderMap = {};
        cardOrder.forEach((cid, i) => { orderMap[cid] = i; });
        ids.sort((a, b) => {
            const aInOrder = a in orderMap;
            const bInOrder = b in orderMap;
            if (aInOrder && bInOrder) return orderMap[a] - orderMap[b];
            if (aInOrder && !bInOrder) return -1;
            if (!aInOrder && bInOrder) return 1;
            // Both new: online first, then alpha
            const ao = machines[a].online ? 0 : 1;
            const bo = machines[b].online ? 0 : 1;
            if (ao !== bo) return ao - bo;
            return (machines[a].client_name || '').localeCompare(machines[b].client_name || '');
        });

        // Build a map of existing cards by client_id
        const existingCards = {};
        dashboardGrid.querySelectorAll('.machine-card').forEach(card => {
            if (card.dataset.clientId) existingCards[card.dataset.clientId] = card;
        });

        // Remove cards for clients that no longer exist
        const idSet = new Set(ids);
        Object.keys(existingCards).forEach(cid => {
            if (!idSet.has(cid)) { existingCards[cid].remove(); delete existingCards[cid]; }
        });

        ids.forEach((id, idx) => {
            const m = machines[id];
            const live = m.live || m;
            const cpuArr = live.cpus || (live.cpu ? [live.cpu] : []);
            const cpu = cpuArr.length === 1 ? cpuArr[0].usage_percent : (cpuArr.length > 1 ? cpuArr.reduce((s, c) => s + (c.usage_percent || 0), 0) / cpuArr.length : null);
            const ram = live.ram ? live.ram.percent : null;

            // Disk total: sum all partitions
            const disks = live.disks || [];
            let diskTotalBytes = 0, diskUsedBytes = 0;
            disks.forEach(d => {
                diskTotalBytes += (d.total_bytes || d.total || 0);
                diskUsedBytes += (d.used_bytes || d.used || 0);
            });
            const diskPercent = diskTotalBytes > 0 ? (diskUsedBytes / diskTotalBytes * 100) : null;

            // Avg temperature across all sensors
            const temps = live.temperatures || {};
            const tempVals = Object.values(temps).map(v => {
                if (typeof v === 'object' && v !== null) return v.current ?? v.value ?? null;
                return typeof v === 'number' ? v : null;
            }).filter(v => v !== null && !isNaN(v));
            const avgTemp = tempVals.length > 0 ? tempVals.reduce((s, v) => s + v, 0) / tempVals.length : null;

            let barsHTML = '';
            if (m.online && cpu !== null) {
                barsHTML += statBar('CPU', cpu);
                barsHTML += statBar('RAM', ram || 0);
                if (diskPercent !== null) barsHTML += statBar('DISK', diskPercent);
                if (avgTemp !== null) barsHTML += statBar('TEMP', Math.min(100, avgTemp), `${Math.round(avgTemp)}°C`);
            }

            const metaLeft = live.os || '';

            let innerHTML;
            if (!m.online) {
                innerHTML = `
                    <div class="machine-card-inner">
                        <div class="card-header">
                            <span class="status-dot offline"></span>
                            <span class="card-name">${esc(m.client_name || m.client_id)}</span>
                        </div>
                        <div class="card-ip">${esc(live.ip || '—')}</div>
                        <div class="card-offline-info">Offline</div>
                    </div>
                `;
            } else {
                innerHTML = `
                    <div class="machine-card-inner">
                        <div class="card-header">
                            <span class="status-dot online"></span>
                            <span class="card-name">${esc(m.client_name || m.client_id)}</span>
                        </div>
                        <div class="card-ip">${esc(live.ip || '—')}</div>
                        ${barsHTML}
                        <div class="card-meta">
                            <span>${esc(metaLeft)}</span>
                        </div>
                    </div>
                `;
            }

            let card = existingCards[id];
            if (card) {
                // Update existing card in-place — no animation replay
                card.className = 'machine-card' + (m.online ? '' : ' offline');
                card.innerHTML = innerHTML;
            } else {
                // New card — create with entrance animation
                card = document.createElement('div');
                card.className = 'machine-card' + (m.online ? '' : ' offline');
                card.dataset.clientId = id;
                card.style.animationDelay = `${idx * 0.06}s`;
                card.innerHTML = innerHTML;
            }

            // (Re-)bind event listeners
            const clone = card.cloneNode(true);
            clone.dataset.clientId = id;
            clone.draggable = true;

            // Drag & Drop
            clone.addEventListener('dragstart', (e) => {
                dragSrcId = id;
                clone.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            });
            clone.addEventListener('dragend', () => {
                clone.classList.remove('dragging');
                dashboardGrid.querySelectorAll('.machine-card').forEach(c => c.classList.remove('drag-over'));
                dragSrcId = null;
                saveCardOrder();
            });
            clone.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                if (dragSrcId && dragSrcId !== id) clone.classList.add('drag-over');
            });
            clone.addEventListener('dragleave', () => clone.classList.remove('drag-over'));
            clone.addEventListener('drop', (e) => {
                e.preventDefault();
                clone.classList.remove('drag-over');
                if (!dragSrcId || dragSrcId === id) return;
                const srcCard = dashboardGrid.querySelector(`[data-client-id="${dragSrcId}"]`);
                if (!srcCard) return;
                const allCards = [...dashboardGrid.querySelectorAll('.machine-card')];
                const srcIdx = allCards.indexOf(srcCard);
                const tgtIdx = allCards.indexOf(clone);
                if (srcIdx < tgtIdx) {
                    clone.after(srcCard);
                } else {
                    clone.before(srcCard);
                }
            });

            if (m.online) {
                clone.addEventListener('click', (e) => {
                    // Don't open detail if we just finished dragging
                    if (e.defaultPrevented) return;
                    openDetail(id);
                });
            } else {
                let pressTimer = null;
                clone.addEventListener('pointerdown', (e) => {
                    pressTimer = setTimeout(() => showContextMenu(e, id), 700);
                });
                clone.addEventListener('pointerup', () => clearTimeout(pressTimer));
                clone.addEventListener('pointerleave', () => clearTimeout(pressTimer));
                clone.addEventListener('click', () => openDetailOffline(id));
            }

            if (existingCards[id]) {
                // Existing card — no entrance animation
                existingCards[id].replaceWith(clone);
            } else {
                // New card — entrance animation
                clone.classList.add('machine-card-enter');
                clone.addEventListener('animationend', () => clone.classList.remove('machine-card-enter'), { once: true });
                dashboardGrid.appendChild(clone);
            }
            existingCards[id] = clone;
        });

        // Reorder if needed (e.g. online/offline status changed)
        ids.forEach((id, idx) => {
            const card = dashboardGrid.querySelector(`[data-client-id="${id}"]`);
            if (card && card !== dashboardGrid.children[idx]) {
                dashboardGrid.insertBefore(card, dashboardGrid.children[idx]);
            }
        });
    }

    function statBar(label, percent, customValue) {
        const p = Math.min(100, Math.max(0, Math.round(percent)));
        const cls = p < 60 ? 'bar-green' : p < 80 ? 'bar-orange' : 'bar-red';
        const display = customValue || `${p}%`;
        return `
            <div class="stat-bar">
                <div class="stat-bar-label"><span>${label}</span><span>${display}</span></div>
                <div class="stat-bar-track"><div class="stat-bar-fill ${cls}" style="width:${p}%"></div></div>
            </div>
        `;
    }

    // ══════════════════════════════════════
    //  CONTEXT MENU (offline long-press)
    // ══════════════════════════════════════
    const ctxMenu = document.getElementById('context-menu');

    function showContextMenu(e, clientId) {
        e.preventDefault();
        ctxMenu.innerHTML = `
            <button class="context-menu-item" data-action="last-info">Letzte Infos anzeigen</button>
            <button class="context-menu-item danger" data-action="delete">Maschine entfernen</button>
        `;
        ctxMenu.style.top = e.clientY + 'px';
        ctxMenu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
        ctxMenu.classList.remove('hidden');

        ctxMenu.querySelectorAll('.context-menu-item').forEach(btn => {
            btn.addEventListener('click', () => {
                ctxMenu.classList.add('hidden');
                if (btn.dataset.action === 'last-info') openDetailOffline(clientId);
                else if (btn.dataset.action === 'delete') deleteMachine(clientId);
            });
        });
    }

    document.addEventListener('click', (e) => {
        if (!ctxMenu.contains(e.target)) ctxMenu.classList.add('hidden');
    });

    async function deleteMachine(clientId) {
        const pw = await askPassword('Maschine entfernen');
        if (!pw) return;
        try {
            await fetch(`/api/machines/${clientId}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: pw })
            });
            delete machines[clientId];
            renderDashboard();
        } catch (e) { }
    }

    // ══════════════════════════════════════
    //  DETAIL VIEW
    // ══════════════════════════════════════
    function openDetail(clientId) {
        currentDetail = clientId;
        const m = machines[clientId];
        if (!m) return;

        logsAuthenticated = false;
        shellAuthenticated = false;

        document.getElementById('detail-title').textContent = m.client_name || clientId;
        updateDetailStatus(m.online);

        // Build tabs based on platform
        const platform = (m.live || m).platform || 'linux';
        const tabs = ['Übersicht', 'Prozesse', 'Sessions', 'Logs', 'Disks', 'Shell', 'Plaintext', 'Aktionen'];
        if (platform !== 'windows') {
            tabs.splice(4, 0, 'Services');
            tabs.splice(tabs.indexOf('Aktionen'), 0, 'Updates');
        }

        const tabContainer = document.getElementById('detail-tabs');
        tabContainer.innerHTML = '';
        const tabMap = {
            'Übersicht': 'overview', 'Prozesse': 'processes', 'Sessions': 'sessions',
            'Logs': 'logs', 'Services': 'services', 'Disks': 'disks',
            'Shell': 'shell', 'Updates': 'updates', 'Aktionen': 'actions',
            'Plaintext': 'plaintext'
        };

        tabs.forEach((t, i) => {
            const btn = document.createElement('button');
            btn.className = 'detail-tab' + (i === 0 ? ' active' : '');
            btn.textContent = t;
            btn.addEventListener('click', () => switchTab(tabMap[t], btn));
            tabContainer.appendChild(btn);
        });

        // Show overview tab
        switchTab('overview', tabContainer.querySelector('.detail-tab'));

        // Populate overview with current data
        const live = m.live || m;
        updateDetailLive(live);

        showPage('detail');
    }

    async function openDetailOffline(clientId) {
        currentDetail = clientId;
        const m = machines[clientId];
        if (!m) return;

        document.getElementById('detail-title').textContent = m.client_name || clientId;
        updateDetailStatus(false);

        const tabContainer = document.getElementById('detail-tabs');
        tabContainer.innerHTML = '';
        const btn = document.createElement('button');
        btn.className = 'detail-tab active';
        btn.textContent = 'Letzte Infos';
        tabContainer.appendChild(btn);

        // Try loading snapshot
        try {
            const res = await fetch(`/api/machines/${clientId}/snapshot`);
            const data = await res.json();
            if (data.snapshot) {
                switchTab('overview', btn);
                updateDetailLive(data.snapshot);
            } else {
                switchTab('overview', btn);
                document.getElementById('overview-stats').innerHTML = '<p style="color:var(--text-secondary);">Keine gespeicherten Daten.</p>';
                document.getElementById('overview-network').innerHTML = '';
            }
        } catch (e) {
            switchTab('overview', btn);
        }

        showPage('detail');
    }

    document.getElementById('detail-back').addEventListener('click', () => {
        currentDetail = null;
        // Stop any streams
        if (ws && ws.readyState === WebSocket.OPEN) {
            // noop for now
        }
        showPage('dashboard');
    });

    function updateDetailStatus(online) {
        const el = document.getElementById('detail-status');
        if (online) {
            el.innerHTML = '<span class="status-dot online" style="width:8px;height:8px;"></span> Online';
            el.style.color = 'var(--color-green)';
        } else {
            el.innerHTML = '<span class="status-dot offline" style="width:8px;height:8px;"></span> Offline';
            el.style.color = 'var(--color-red)';
        }
    }

    function switchTab(tabId, btnEl) {
        document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
        document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
        if (btnEl) btnEl.classList.add('active');

        const tc = document.getElementById('tab-' + tabId);
        if (tc) tc.classList.add('active');

        // On-demand loading
        if (tabId === 'processes') requestOnDemand('processes');
        if (tabId === 'services') requestOnDemand('services');
        if (tabId === 'updates') requestOnDemand('updates');
        if (tabId === 'disks') requestOnDemand('disk_check');
        if (tabId === 'logs') handleLogsTab();
        if (tabId === 'shell') handleShellTab();
    }

    async function requestOnDemand(type) {
        if (!currentDetail) return;
        try {
            await fetch(`/api/request/${currentDetail}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type })
            });
        } catch (e) { }
    }

    async function handleLogsTab() {
        if (logsAuthenticated) return;
        const pw = await askPassword('Logs anzeigen');
        if (!pw) {
            const overviewBtn = document.querySelector('.detail-tab');
            switchTab('overview', overviewBtn);
            return;
        }
        logsAuthenticated = true;
        document.getElementById('logs-output').textContent = '';
        try {
            await fetch(`/api/request/${currentDetail}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: 'logs', password: pw })
            });
        } catch (e) { }
    }

    async function handleShellTab() {
        if (shellAuthenticated) return;
        const pw = await askPassword('Shell-Zugriff');
        if (!pw) {
            const overviewBtn = document.querySelector('.detail-tab');
            switchTab('overview', overviewBtn);
            return;
        }
        shellAuthenticated = true;
        document.getElementById('shell-output').textContent = '';
        try {
            await fetch(`/api/request/${currentDetail}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: 'shell', password: pw })
            });
        } catch (e) { }
    }

    // Shell input
    document.getElementById('shell-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && shellAuthenticated && ws && ws.readyState === WebSocket.OPEN && currentDetail) {
            ws.send(JSON.stringify({
                type: 'shell_input',
                client_id: currentDetail,
                data: e.target.value + '\n'
            }));
            e.target.value = '';
        }
    });

    // Logs filter
    document.getElementById('logs-filter').addEventListener('input', (e) => {
        const filter = e.target.value.toLowerCase();
        const lines = document.getElementById('logs-output').querySelectorAll('.log-line');
        lines.forEach(l => {
            l.style.display = l.textContent.toLowerCase().includes(filter) || !filter ? '' : 'none';
        });
    });

    function appendLog(text) {
        const el = document.getElementById('logs-output');
        const line = document.createElement('div');
        line.className = 'log-line';
        line.textContent = text;
        el.appendChild(line);
        if (logsAutoScroll) el.scrollTop = el.scrollHeight;
    }

    function appendShell(text) {
        const el = document.getElementById('shell-output');
        el.textContent += text;
        el.scrollTop = el.scrollHeight;
    }

    // Auto-scroll pause for logs
    const logsEl = document.getElementById('logs-output');
    logsEl.addEventListener('scroll', () => {
        logsAutoScroll = (logsEl.scrollHeight - logsEl.scrollTop - logsEl.clientHeight) < 30;
    });

    // ══════════════════════════════════════
    //  DETAIL: Live data update
    // ══════════════════════════════════════
    function updateDetailLive(data) {
        const stats = document.getElementById('overview-stats');
        const cpusEl = document.getElementById('overview-cpus');
        const gpusEl = document.getElementById('overview-gpus');
        const tempsEl = document.getElementById('overview-temps');
        const netEl = document.getElementById('overview-network');

        // ── Top-level stat cards ──
        const ram = data.ram || {};
        const load = data.load_avg;
        const uptime = data.uptime_seconds;

        let html = '';
        html += statCard('RAM', `${Math.round(ram.used_mb || 0)} / ${Math.round(ram.total_mb || 0)} MB`, `${Math.round(ram.percent || 0)}%`);
        if (uptime != null) html += statCard('Uptime', formatUptime(uptime));
        if (load) html += statCard('Load', `${load[0]?.toFixed(2) || '—'}  ${load[1]?.toFixed(2) || '—'}  ${load[2]?.toFixed(2) || '—'}`, '1m / 5m / 15m');
        const users = data.users || [];
        if (users.length) html += statCard('Sessions', `${users.length} aktiv`);
        html += statCard('OS', data.os || '—', data.hostname || '');
        html += statCard('IP', data.ip || '—');
        stats.innerHTML = html;

        // ── CPUs (multi-CPU support) ──
        // Support both `cpu` (single object) and `cpus` (array of objects)
        const cpuList = data.cpus || (data.cpu ? [data.cpu] : []);
        if (cpuList.length) {
            let cpuHtml = '<h4 style="color:var(--text-heading);margin-bottom:12px;">CPUs</h4>';
            cpuList.forEach((cpu, idx) => {
                const label = cpuList.length > 1 ? `CPU ${idx}` : 'CPU';
                cpuHtml += `<div class="hw-block glass">`;
                cpuHtml += `<div class="hw-block-header">`;
                cpuHtml += `<span class="hw-block-title">${esc(label)}: ${esc(cpu.model || '—')}</span>`;
                cpuHtml += `<span class="hw-block-value">${Math.round(cpu.usage_percent || 0)}% · ${cpu.cores || '?'} Kerne${cpu.freq_mhz ? ' · ' + cpu.freq_mhz + ' MHz' : ''}</span>`;
                cpuHtml += `</div>`;

                // Overall bar
                cpuHtml += miniBar('Gesamt', cpu.usage_percent || 0);

                // Per-core bars
                const perCore = cpu.per_core || [];
                if (perCore.length) {
                    cpuHtml += `<div class="per-core-grid">`;
                    perCore.forEach((v, ci) => {
                        cpuHtml += miniBarCompact(`K${ci}`, v);
                    });
                    cpuHtml += `</div>`;
                }

                cpuHtml += `</div>`;
            });
            cpusEl.innerHTML = cpuHtml;
        } else {
            cpusEl.innerHTML = '';
        }

        // ── GPUs (multi-GPU support) ──
        const gpus = data.gpus || [];
        if (gpus.length) {
            let gpuHtml = '<h4 style="color:var(--text-heading);margin-bottom:12px;">GPUs</h4>';
            gpus.forEach((g, idx) => {
                gpuHtml += `<div class="hw-block glass">`;
                gpuHtml += `<div class="hw-block-header">`;
                gpuHtml += `<span class="hw-block-title">GPU ${idx}: ${esc(g.name || '—')}</span>`;
                gpuHtml += `<span class="hw-block-value">${g.temp_c != null ? g.temp_c + '°C' : ''}</span>`;
                gpuHtml += `</div>`;

                if (g.usage_percent != null) gpuHtml += miniBar('Auslastung', g.usage_percent);
                if (g.vram_total_mb) {
                    const vramPct = (g.vram_used_mb / g.vram_total_mb * 100) || 0;
                    gpuHtml += miniBar(`VRAM (${g.vram_used_mb || 0} / ${g.vram_total_mb} MB)`, vramPct);
                }
                if (g.power_draw_w != null) gpuHtml += `<div class="hw-detail">Power: ${g.power_draw_w}W${g.power_limit_w ? ' / ' + g.power_limit_w + 'W' : ''}</div>`;
                if (g.fan_speed_percent != null) gpuHtml += `<div class="hw-detail">Lüfter: ${g.fan_speed_percent}%</div>`;
                if (g.encoder_percent != null) gpuHtml += `<div class="hw-detail">Encoder: ${g.encoder_percent}% · Decoder: ${g.decoder_percent || 0}%</div>`;
                if (g.pcie_gen) gpuHtml += `<div class="hw-detail">PCIe Gen${g.pcie_gen} x${g.pcie_width || '?'}</div>`;
                if (g.driver) gpuHtml += `<div class="hw-detail">Treiber: ${esc(g.driver)}</div>`;
                if (g.cuda_version) gpuHtml += `<div class="hw-detail">CUDA: ${esc(g.cuda_version)}</div>`;

                // Additional arbitrary key-value pairs the client sends
                const knownKeys = ['name','usage_percent','vram_used_mb','vram_total_mb','temp_c','power_draw_w','power_limit_w','fan_speed_percent','encoder_percent','decoder_percent','pcie_gen','pcie_width','driver','cuda_version'];
                Object.keys(g).forEach(k => {
                    if (!knownKeys.includes(k)) {
                        gpuHtml += `<div class="hw-detail">${esc(k)}: ${esc(String(g[k]))}</div>`;
                    }
                });

                gpuHtml += `</div>`;
            });
            gpusEl.innerHTML = gpuHtml;
        } else {
            gpusEl.innerHTML = '';
        }

        // ── Temperatures (all sensors) ──
        const temps = data.temperatures || {};
        const tempKeys = Object.keys(temps);
        if (tempKeys.length) {
            let tempHtml = '<h4 style="color:var(--text-heading);margin-bottom:12px;">Temperaturen</h4>';
            tempHtml += '<div class="temps-grid">';
            tempKeys.forEach(key => {
                const val = temps[key];
                // Support both number and object {current, high, critical}
                if (typeof val === 'object' && val !== null) {
                    const c = val.current ?? val.value ?? 0;
                    const high = val.high;
                    const crit = val.critical;
                    let color = 'var(--color-green)';
                    if (crit && c >= crit) color = 'var(--color-red)';
                    else if (high && c >= high) color = 'var(--color-orange)';
                    else if (c >= 80) color = 'var(--color-red)';
                    else if (c >= 60) color = 'var(--color-orange)';
                    tempHtml += `<div class="temp-chip"><span class="temp-label">${esc(key)}</span><span class="temp-value" style="color:${color}">${Math.round(c)}°C</span>`;
                    if (high || crit) tempHtml += `<span class="temp-limits">${high ? 'H:' + high + '°' : ''}${crit ? ' C:' + crit + '°' : ''}</span>`;
                    tempHtml += `</div>`;
                } else {
                    const c = Number(val) || 0;
                    const color = c >= 80 ? 'var(--color-red)' : c >= 60 ? 'var(--color-orange)' : 'var(--color-green)';
                    tempHtml += `<div class="temp-chip"><span class="temp-label">${esc(key)}</span><span class="temp-value" style="color:${color}">${Math.round(c)}°C</span></div>`;
                }
            });
            tempHtml += '</div>';
            tempsEl.innerHTML = tempHtml;
        } else {
            tempsEl.innerHTML = '';
        }

        // ── Disks (also update if tab visible) ──
        const disks = data.disks || [];
        if (document.getElementById('tab-disks').classList.contains('active')) {
            renderDisks(disks);
        }

        // ── Network ──
        const net = data.network || {};
        const interfaces = net.interfaces || [];
        if (interfaces.length) {
            netEl.innerHTML = interfaces.map(iface => `
                <div class="interface-row">
                    <span class="interface-name">${esc(iface.name)}</span>
                    <span>${esc(iface.ip || '—')}</span>
                    <span style="color:var(--color-green);">↓ ${formatBytes(iface.rx_bytes)}</span>
                    <span style="color:var(--color-orange);">↑ ${formatBytes(iface.tx_bytes)}</span>
                </div>
            `).join('');
        } else {
            netEl.innerHTML = '';
        }

        // ── Sessions ──
        if (document.getElementById('tab-sessions').classList.contains('active')) {
            renderSessions(users);
        }

        // ── Plaintext ──
        if (data.plaintext != null) {
            document.getElementById('plaintext-output').textContent = typeof data.plaintext === 'string' ? data.plaintext : JSON.stringify(data.plaintext, null, 2);
        }
    }

    function statCard(label, value, sub) {
        return `
            <div class="stat-card">
                <div class="stat-card-label">${esc(label)}</div>
                <div class="stat-card-value">${esc(String(value))}</div>
                ${sub ? `<div class="stat-card-sub">${esc(String(sub))}</div>` : ''}
            </div>
        `;
    }

    function miniBar(label, percent) {
        const p = Math.min(100, Math.max(0, Math.round(percent)));
        const cls = p < 60 ? 'bar-green' : p < 80 ? 'bar-orange' : 'bar-red';
        return `
            <div class="stat-bar" style="margin:8px 0;">
                <div class="stat-bar-label"><span>${esc(label)}</span><span>${p}%</span></div>
                <div class="stat-bar-track"><div class="stat-bar-fill ${cls}" style="width:${p}%"></div></div>
            </div>
        `;
    }

    function miniBarCompact(label, percent) {
        const p = Math.min(100, Math.max(0, Math.round(percent)));
        const cls = p < 60 ? 'bar-green' : p < 80 ? 'bar-orange' : 'bar-red';
        return `
            <div class="core-bar">
                <span class="core-label">${label}</span>
                <div class="stat-bar-track" style="flex:1;"><div class="stat-bar-fill ${cls}" style="width:${p}%"></div></div>
                <span class="core-pct">${p}%</span>
            </div>
        `;
    }

    // ══════════════════════════════════════
    //  DETAIL: Processes
    // ══════════════════════════════════════
    let processSortCol = 'cpu_percent';
    let processSortAsc = false;

    function renderProcesses(procs) {
        if (!procs || !procs.length) {
            document.getElementById('process-table-wrap').innerHTML = '<p style="color:var(--text-secondary);padding:20px;">Keine Prozesse.</p>';
            return;
        }

        // Sort
        procs.sort((a, b) => {
            const va = a[processSortCol] ?? 0;
            const vb = b[processSortCol] ?? 0;
            if (typeof va === 'string') return processSortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
            return processSortAsc ? va - vb : vb - va;
        });

        const cols = [
            { key: 'pid', label: 'PID' },
            { key: 'name', label: 'Name' },
            { key: 'cpu_percent', label: 'CPU%' },
            { key: 'ram_percent', label: 'RAM%' },
            { key: 'user', label: 'User' }
        ];

        let html = '<table><thead><tr>';
        cols.forEach(c => {
            const arrow = processSortCol === c.key ? (processSortAsc ? ' ↑' : ' ↓') : '';
            html += `<th data-col="${c.key}">${c.label}${arrow}</th>`;
        });
        html += '</tr></thead><tbody>';
        procs.forEach(p => {
            html += `<tr>
                <td>${p.pid}</td>
                <td>${esc(p.name || '—')}</td>
                <td>${(p.cpu_percent || 0).toFixed(1)}</td>
                <td>${(p.ram_percent || 0).toFixed(1)}</td>
                <td>${esc(p.user || '—')}</td>
            </tr>`;
        });
        html += '</tbody></table>';

        const wrap = document.getElementById('process-table-wrap');
        wrap.innerHTML = html;

        wrap.querySelectorAll('th').forEach(th => {
            th.addEventListener('click', () => {
                const col = th.dataset.col;
                if (processSortCol === col) processSortAsc = !processSortAsc;
                else { processSortCol = col; processSortAsc = false; }
                renderProcesses(procs);
            });
        });
    }

    // ══════════════════════════════════════
    //  DETAIL: Sessions
    // ══════════════════════════════════════
    function renderSessions(users) {
        const el = document.getElementById('sessions-list');
        if (!users || !users.length) {
            el.innerHTML = '<p style="color:var(--text-secondary);">Keine aktiven Sessions.</p>';
            return;
        }
        el.innerHTML = users.map(u => `
            <div class="list-item">
                <div class="list-item-info">
                    <div class="list-item-title">${esc(u.name)}</div>
                    <div class="list-item-meta">${esc(u.terminal || '—')} · ${esc(u.host || '—')} · seit ${esc(u.started || '—')}</div>
                </div>
                <div class="list-item-actions">
                    <button class="btn-danger btn-danger-sm" onclick="window._kickUser('${esc(u.name)}','${esc(u.terminal || '')}')">Kick</button>
                </div>
            </div>
        `).join('');
    }

    window._kickUser = async (user, terminal) => {
        const pw = await askPassword(`Session von ${user} beenden`);
        if (!pw) return;
        const ok = await askConfirm(`Session von ${user} auf ${terminal} beenden?`, 'Ja, beenden', 'Abbrechen');
        if (!ok) return;
        try {
            await fetch(`/api/action/${currentDetail}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'kick_user', password: pw, params: { user, terminal } })
            });
        } catch (e) { }
    };

    // ══════════════════════════════════════
    //  DETAIL: Services
    // ══════════════════════════════════════
    function renderServices(services) {
        const el = document.getElementById('services-list');
        if (!services || !services.length) {
            el.innerHTML = '<p style="color:var(--text-secondary);">Keine Services.</p>';
            return;
        }
        el.innerHTML = services.map(s => {
            const dotColor = s.state === 'active' || s.state === 'running' ? 'var(--color-green)'
                           : s.state === 'failed' ? 'var(--color-red)' : 'var(--text-secondary)';
            return `
                <div class="list-item">
                    <span class="service-dot" style="background:${dotColor};"></span>
                    <div class="list-item-info">
                        <div class="list-item-title">${esc(s.name)}</div>
                        <div class="list-item-meta">${esc(s.state || '—')} ${s.sub ? '(' + esc(s.sub) + ')' : ''}</div>
                    </div>
                    <div class="list-item-actions">
                        <button class="btn-outline btn-outline-sm" onclick="window._restartService('${esc(s.name)}')">Restart</button>
                    </div>
                </div>
            `;
        }).join('');
    }

    window._restartService = async (name) => {
        const pw = await askPassword(`Service ${name} neustarten`);
        if (!pw) return;
        const ok = await askConfirm(`Service ${name} neustarten?`, 'Ja, Restart', 'Abbrechen');
        if (!ok) return;
        try {
            await fetch(`/api/action/${currentDetail}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'service_restart', password: pw, params: { service_name: name } })
            });
        } catch (e) { }
    };

    // ══════════════════════════════════════
    //  DETAIL: Disks
    // ══════════════════════════════════════
    function renderDisks(disks) {
        const el = document.getElementById('disks-list');
        if (!disks || !disks.length) {
            el.innerHTML = '<p style="color:var(--text-secondary);">Keine Disks.</p>';
            return;
        }
        el.innerHTML = disks.map(d => {
            const p = Math.round(d.percent || 0);
            const cls = p < 60 ? 'bar-green' : p < 80 ? 'bar-orange' : 'bar-red';
            return `
                <div class="disk-block">
                    <div class="disk-mount">${esc(d.mount || '—')}</div>
                    <div class="disk-info">
                        <span>${esc(d.fs_type || '')} · ${(d.used_gb || 0).toFixed(1)} / ${(d.total_gb || 0).toFixed(1)} GB</span>
                        <span>${p}%</span>
                    </div>
                    <div class="stat-bar-track"><div class="stat-bar-fill ${cls}" style="width:${p}%"></div></div>
                </div>
            `;
        }).join('');
    }

    // ══════════════════════════════════════
    //  DETAIL: S.M.A.R.T.
    // ══════════════════════════════════════
    function renderSmart(data) {
        const section = document.getElementById('smart-section');
        const el = document.getElementById('smart-list');
        if (!data || (!data.drives && !Array.isArray(data))) {
            // If it's raw text, show in terminal style
            if (typeof data === 'string') {
                section.classList.remove('hidden');
                el.innerHTML = `
                    <div class="terminal-container">
                        <div class="terminal-header">
                            <div class="traffic-lights"><span></span><span></span><span></span></div>
                            <span class="terminal-title">smartctl</span>
                        </div>
                        <div class="terminal-body" style="color:var(--text-primary);max-height:600px;">${esc(data)}</div>
                    </div>
                `;
                return;
            }
            section.classList.add('hidden');
            return;
        }

        section.classList.remove('hidden');
        const drives = Array.isArray(data) ? data : (data.drives || []);

        el.innerHTML = drives.map(drive => {
            let html = `<div class="hw-block glass" style="margin-bottom:16px;">`;
            html += `<div class="hw-block-header">`;
            html += `<span class="hw-block-title">${esc(drive.device || drive.name || '—')}</span>`;

            // Health status with color
            const health = (drive.health || drive.smart_status || '').toLowerCase();
            const healthColor = health.includes('pass') || health.includes('ok') ? 'var(--color-green)' : 'var(--color-red)';
            html += `<span class="hw-block-value" style="color:${healthColor}">${esc(drive.health || drive.smart_status || '—')}</span>`;
            html += `</div>`;

            // Basic info
            if (drive.model) html += `<div class="hw-detail">Modell: ${esc(drive.model)}</div>`;
            if (drive.serial) html += `<div class="hw-detail">Serial: ${esc(drive.serial)}</div>`;
            if (drive.firmware) html += `<div class="hw-detail">Firmware: ${esc(drive.firmware)}</div>`;
            if (drive.capacity) html += `<div class="hw-detail">Kapazität: ${esc(drive.capacity)}</div>`;
            if (drive.temperature != null) html += `<div class="hw-detail">Temperatur: ${drive.temperature}°C</div>`;
            if (drive.power_on_hours != null) html += `<div class="hw-detail">Betriebsstunden: ${drive.power_on_hours.toLocaleString()}h</div>`;
            if (drive.power_cycle_count != null) html += `<div class="hw-detail">Power Cycles: ${drive.power_cycle_count}</div>`;
            if (drive.reallocated_sectors != null) {
                const rsColor = drive.reallocated_sectors > 0 ? 'var(--color-red)' : 'var(--color-green)';
                html += `<div class="hw-detail">Reallocated Sectors: <span style="color:${rsColor}">${drive.reallocated_sectors}</span></div>`;
            }
            if (drive.wear_leveling != null) html += `<div class="hw-detail">Wear Leveling: ${drive.wear_leveling}%</div>`;

            // Full SMART attributes table
            const attrs = drive.attributes || [];
            if (attrs.length) {
                html += `<div class="smart-attrs-scroll"><table class="smart-table"><thead><tr>`;
                html += `<th>ID</th><th>Attribut</th><th>Wert</th><th>Worst</th><th>Thresh</th><th>Raw</th>`;
                html += `</tr></thead><tbody>`;
                attrs.forEach(a => {
                    const failing = a.thresh && a.value < a.thresh;
                    const rowCls = failing ? 'style="color:var(--color-red);"' : '';
                    html += `<tr ${rowCls}>`;
                    html += `<td>${a.id || ''}</td>`;
                    html += `<td>${esc(a.name || '')}</td>`;
                    html += `<td>${a.value ?? ''}</td>`;
                    html += `<td>${a.worst ?? ''}</td>`;
                    html += `<td>${a.thresh ?? ''}</td>`;
                    html += `<td>${esc(String(a.raw ?? ''))}</td>`;
                    html += `</tr>`;
                });
                html += `</tbody></table></div>`;
            }

            // Raw output if provided
            if (drive.raw_output) {
                html += `<details style="margin-top:8px;"><summary style="color:var(--text-secondary);cursor:pointer;font-size:0.8rem;">Raw Output</summary>`;
                html += `<pre style="font-size:0.75rem;color:var(--text-secondary);margin-top:6px;white-space:pre-wrap;">${esc(drive.raw_output)}</pre></details>`;
            }

            // Any extra keys the client sends
            const knownKeys = ['device','name','health','smart_status','model','serial','firmware','capacity','temperature','power_on_hours','power_cycle_count','reallocated_sectors','wear_leveling','attributes','raw_output'];
            Object.keys(drive).forEach(k => {
                if (!knownKeys.includes(k) && typeof drive[k] !== 'object') {
                    html += `<div class="hw-detail">${esc(k)}: ${esc(String(drive[k]))}</div>`;
                }
            });

            html += `</div>`;
            return html;
        }).join('');
    }

    // ══════════════════════════════════════
    //  DETAIL: Updates
    // ══════════════════════════════════════
    function renderUpdates(data) {
        const info = document.getElementById('updates-info');
        const list = document.getElementById('updates-list');
        const action = document.getElementById('updates-action');
        const pkgs = data.packages || [];

        info.innerHTML = `<p style="color:var(--text-heading);font-size:1.1rem;margin-bottom:16px;">Verfügbare Updates: ${pkgs.length} Pakete</p>`;

        if (!pkgs.length) {
            list.innerHTML = '<p style="color:var(--text-secondary);">Keine Updates verfügbar.</p>';
            action.innerHTML = '';
            return;
        }

        list.innerHTML = pkgs.map(p => `
            <div class="list-item">
                <div class="list-item-info">
                    <div class="list-item-title">${esc(p.name)}</div>
                    <div class="list-item-meta">${esc(p.current || '?')} → ${esc(p.available || '?')}</div>
                </div>
            </div>
        `).join('');

        action.innerHTML = '<button class="btn-gradient" id="update-all-btn">Alle Pakete updaten</button>';
        document.getElementById('update-all-btn').addEventListener('click', async () => {
            const pw = await askPassword('Pakete updaten');
            if (!pw) return;
            const ok = await askConfirm('Alle Pakete jetzt updaten?', 'Ja, updaten', 'Abbrechen');
            if (!ok) return;
            document.getElementById('updates-terminal').classList.remove('hidden');
            document.getElementById('updates-output').textContent = 'Update wird gestartet...\n';
            try {
                await fetch(`/api/action/${currentDetail}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'update_packages', password: pw })
                });
            } catch (e) { }
        });
    }

    // ══════════════════════════════════════
    //  DETAIL: Actions (Reboot/Shutdown)
    // ══════════════════════════════════════
    document.getElementById('action-reboot').addEventListener('click', async () => {
        const m = machines[currentDetail];
        if (!m) return;
        const pw = await askPassword('Reboot bestätigen');
        if (!pw) return;
        const ok = await askConfirm(`Bist du sicher, dass du ${m.client_name || currentDetail} neustarten willst?`, 'Ja, Reboot', 'Abbrechen');
        if (!ok) return;
        try {
            await fetch(`/api/action/${currentDetail}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'reboot', password: pw })
            });
        } catch (e) { }
    });

    document.getElementById('action-shutdown').addEventListener('click', async () => {
        const m = machines[currentDetail];
        if (!m) return;
        const pw = await askPassword('Shutdown bestätigen');
        if (!pw) return;
        const ok1 = await askConfirm(`Bist du sicher, dass du ${m.client_name || currentDetail} herunterfahren willst?`, 'Ja, weiter', 'Abbrechen');
        if (!ok1) return;
        const ok2 = await askConfirm('WIRKLICH sicher? Die Maschine kann remote nicht wieder eingeschaltet werden!', 'Ja, Shutdown', 'Abbrechen', true);
        if (!ok2) return;
        try {
            await fetch(`/api/action/${currentDetail}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'shutdown', password: pw })
            });
        } catch (e) { }
    });

    // ══════════════════════════════════════
    //  SETTINGS
    // ══════════════════════════════════════
    async function loadSettings() {
        try {
            const res = await fetch('/api/settings');
            const data = await res.json();
            document.getElementById('settings-api-key').textContent = data.api_key || '—';
            document.getElementById('set-telemetry').value = data.telemetry_interval || 3;
            document.getElementById('set-snapshot').value = data.snapshot_interval || 5;
        } catch (e) { }
    }

    document.getElementById('set-pw-btn').addEventListener('click', async () => {
        const cur = document.getElementById('set-pw-current').value;
        const nw = document.getElementById('set-pw-new').value;
        const cf = document.getElementById('set-pw-confirm').value;
        const msg = document.getElementById('set-pw-msg');

        if (nw.length < 4) { msg.innerHTML = '<span class="error-msg">Neues Passwort zu kurz</span>'; return; }
        if (nw !== cf) { msg.innerHTML = '<span class="error-msg">Passwörter stimmen nicht überein</span>'; return; }

        try {
            const res = await fetch('/api/settings/password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ current_password: cur, new_password: nw })
            });
            if (res.ok) {
                cachedPassword = null;
                msg.innerHTML = '<span class="success-msg">Passwort geändert!</span>';
                document.getElementById('set-pw-current').value = '';
                document.getElementById('set-pw-new').value = '';
                document.getElementById('set-pw-confirm').value = '';
            } else {
                msg.innerHTML = '<span class="error-msg">Falsches aktuelles Passwort</span>';
            }
        } catch (e) {
            msg.innerHTML = '<span class="error-msg">Fehler</span>';
        }
    });

    document.getElementById('set-key-btn').addEventListener('click', async () => {
        const pw = await askPassword('Key regenerieren', 'Passwort eingeben, um den API-Key zu regenerieren.', true);
        if (!pw) return;
        const currentKey = document.getElementById('settings-api-key').textContent;
        const keyOk = await askApiKeyConfirm(currentKey);
        if (!keyOk) return;
        const msg = document.getElementById('set-key-msg');
        try {
            const res = await fetch('/api/settings/regenerate-key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: pw })
            });
            const data = await res.json();
            if (data.api_key) {
                document.getElementById('settings-api-key').textContent = data.api_key;
                msg.innerHTML = '<span class="success-msg">Neuer Key generiert!</span>';
            } else {
                msg.innerHTML = '<span class="error-msg">Fehler</span>';
            }
        } catch (e) {
            msg.innerHTML = '<span class="error-msg">Fehler</span>';
        }
    });

    document.getElementById('set-intervals-btn').addEventListener('click', async () => {
        const pw = await askPassword('Intervalle ändern', 'Passwort eingeben, um Intervalle zu speichern.', true);
        if (!pw) return;
        const t = document.getElementById('set-telemetry').value;
        const s = document.getElementById('set-snapshot').value;
        const msg = document.getElementById('set-intervals-msg');
        try {
            const res = await fetch('/api/settings/intervals', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ telemetry_interval: parseInt(t), snapshot_interval: parseInt(s), password: pw })
            });
            if (res.ok) {
                msg.innerHTML = '<span class="success-msg">Gespeichert!</span>';
                setTimeout(() => { msg.innerHTML = ''; }, 2000);
            } else {
                msg.innerHTML = '<span class="error-msg">Falsches Passwort</span>';
            }
        } catch (e) {
            msg.innerHTML = '<span class="error-msg">Fehler</span>';
        }
    });

    // ══════════════════════════════════════
    //  MODALS
    // ══════════════════════════════════════
    function askPassword(title, desc, forcePrompt) {
        if (!forcePrompt && cachedPassword) return Promise.resolve(cachedPassword);
        return new Promise(resolve => {
            const overlay = document.getElementById('modal-password');
            document.getElementById('modal-pw-title').textContent = title || 'Passwort bestätigen';
            document.getElementById('modal-pw-desc').textContent = desc || '';
            document.getElementById('modal-pw-input').value = '';
            document.getElementById('modal-pw-error').textContent = '';
            overlay.classList.add('active');

            const input = document.getElementById('modal-pw-input');
            setTimeout(() => input.focus(), 100);

            function cleanup() {
                overlay.classList.remove('active');
                document.getElementById('modal-pw-confirm').replaceWith(document.getElementById('modal-pw-confirm').cloneNode(true));
                document.getElementById('modal-pw-cancel').replaceWith(document.getElementById('modal-pw-cancel').cloneNode(true));
            }

            document.getElementById('modal-pw-confirm').addEventListener('click', async () => {
                const pw = input.value;
                if (!pw) {
                    document.getElementById('modal-pw-error').textContent = 'Passwort eingeben';
                    return;
                }
                // Verify
                try {
                    const res = await fetch('/api/verify-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ password: pw })
                    });
                    const data = await res.json();
                    if (data.valid) {
                        cachedPassword = pw;
                        cleanup();
                        resolve(pw);
                    } else {
                        document.getElementById('modal-pw-error').textContent = 'Falsches Passwort';
                    }
                } catch (e) {
                    document.getElementById('modal-pw-error').textContent = 'Fehler';
                }
            }, { once: true });

            document.getElementById('modal-pw-cancel').addEventListener('click', () => {
                cleanup();
                resolve(null);
            }, { once: true });

            overlay.querySelector('.modal-backdrop').addEventListener('click', () => {
                cleanup();
                resolve(null);
            }, { once: true });

            // Enter key
            input.addEventListener('keydown', function handler(e) {
                if (e.key === 'Enter') {
                    document.getElementById('modal-pw-confirm').click();
                    input.removeEventListener('keydown', handler);
                }
                if (e.key === 'Escape') {
                    cleanup();
                    resolve(null);
                    input.removeEventListener('keydown', handler);
                }
            });
        });
    }

    function askConfirm(text, confirmLabel, cancelLabel, danger) {
        return new Promise(resolve => {
            const overlay = document.getElementById('modal-confirm');
            document.getElementById('modal-cf-title').textContent = 'Bestätigung';
            document.getElementById('modal-cf-desc').textContent = text;

            const btns = document.getElementById('modal-cf-buttons');
            btns.innerHTML = `
                <button class="btn-outline" id="cf-cancel">${esc(cancelLabel || 'Abbrechen')}</button>
                <button class="${danger ? 'btn-danger' : 'btn-gradient'}" id="cf-confirm">${esc(confirmLabel || 'Bestätigen')}</button>
            `;
            overlay.classList.add('active');

            function cleanup() { overlay.classList.remove('active'); }

            document.getElementById('cf-confirm').addEventListener('click', () => { cleanup(); resolve(true); }, { once: true });
            document.getElementById('cf-cancel').addEventListener('click', () => { cleanup(); resolve(false); }, { once: true });
            overlay.querySelector('.modal-backdrop').addEventListener('click', () => { cleanup(); resolve(false); }, { once: true });

            document.addEventListener('keydown', function handler(e) {
                if (e.key === 'Escape') {
                    cleanup();
                    resolve(false);
                    document.removeEventListener('keydown', handler);
                }
            });
        });
    }

    // ══════════════════════════════════════
    //  HELPERS
    // ══════════════════════════════════════

    function askApiKeyConfirm(currentKey) {
        return new Promise(resolve => {
            const overlay = document.getElementById('modal-apikey');
            const input = document.getElementById('modal-ak-input');
            const error = document.getElementById('modal-ak-error');
            input.value = '';
            error.textContent = '';
            overlay.classList.add('active');
            setTimeout(() => input.focus(), 100);

            function cleanup() { overlay.classList.remove('active'); }

            document.getElementById('modal-ak-confirm').addEventListener('click', () => {
                if (input.value.trim() !== currentKey) {
                    error.textContent = 'API-Key stimmt nicht überein';
                    return;
                }
                cleanup();
                resolve(true);
            }, { once: true });

            document.getElementById('modal-ak-cancel').addEventListener('click', () => {
                cleanup();
                resolve(false);
            }, { once: true });

            overlay.querySelector('.modal-backdrop').addEventListener('click', () => {
                cleanup();
                resolve(false);
            }, { once: true });

            input.addEventListener('keydown', function handler(e) {
                if (e.key === 'Enter') {
                    document.getElementById('modal-ak-confirm').click();
                    input.removeEventListener('keydown', handler);
                }
                if (e.key === 'Escape') {
                    cleanup();
                    resolve(false);
                    input.removeEventListener('keydown', handler);
                }
            });
        });
    }
    function esc(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    function formatUptime(seconds) {
        const d = Math.floor(seconds / 86400);
        const h = Math.floor((seconds % 86400) / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (d > 0) return `${d}d ${h}h`;
        if (h > 0) return `${h}h ${m}m`;
        return `${m}m`;
    }

    function formatBytes(bytes) {
        if (bytes == null) return '—';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
        return (bytes / 1073741824).toFixed(2) + ' GB';
    }

    // ══════════════════════════════════════
    //  START
    // ══════════════════════════════════════
    init();
});
