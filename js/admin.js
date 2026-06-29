document.addEventListener('DOMContentLoaded', function () {
    refreshDashboard();
    refreshOrders();
    refreshMenu();
    refreshTables();
    setInterval(function () {
        refreshDashboard();
        refreshOrders();
    }, 3000);
});

function switchTab(tabName, el) {
    document.querySelectorAll('.tab-content').forEach(function (t) { t.classList.remove('active'); });
    document.querySelectorAll('.nav-item').forEach(function (n) { n.classList.remove('active'); });
    document.getElementById('tab-' + tabName).classList.add('active');
    if (el) el.classList.add('active');

    if (tabName === 'dashboard') refreshDashboard();
    if (tabName === 'orders') refreshOrders();
    if (tabName === 'menu') refreshMenu();
    if (tabName === 'tables') refreshTables();
}

function refreshDashboard() {
    var orders = DineFlow.getOrders();
    var menu = DineFlow.getMenu();
    var today = new Date().toDateString();

    var todayOrders = orders.filter(function (o) {
        return new Date(o.timestamp).toDateString() === today;
    });

    var revenue = todayOrders.reduce(function (sum, o) { return sum + (o.total || 0); }, 0);
    var pending = todayOrders.filter(function (o) { return o.status === 'new' || o.status === 'preparing'; }).length;

    document.getElementById('stat-revenue').textContent = DineFlow.formatPrice(revenue);
    document.getElementById('stat-orders').textContent = todayOrders.length;
    document.getElementById('stat-pending').textContent = pending;
    document.getElementById('stat-items').textContent = menu.length;

    var recentHtml = '';
    var recent = orders.slice(0, 8);
    if (recent.length === 0) {
        recentHtml = '<p class="empty-state">No orders yet. Share a table QR code to get started!</p>';
    }
    recent.forEach(function (o) {
        var statusClass = 'status-' + o.status;
        recentHtml += '<div class="recent-order-item">';
        recentHtml += '<div class="ro-left">';
        recentHtml += '<strong>#' + o.id + '</strong> &middot; Table ' + o.table;
        recentHtml += '<span class="ro-time">' + DineFlow.timeAgo(o.timestamp) + '</span>';
        recentHtml += '</div>';
        recentHtml += '<div class="ro-right">';
        recentHtml += '<span class="status-badge ' + statusClass + '">' + o.status + '</span>';
        recentHtml += '<span class="ro-total">' + DineFlow.formatPrice(o.total) + '</span>';
        recentHtml += '</div></div>';
    });
    document.getElementById('recent-orders').innerHTML = recentHtml;

    var itemCounts = {};
    orders.forEach(function (o) {
        (o.items || []).forEach(function (item) {
            if (!itemCounts[item.name]) itemCounts[item.name] = { count: 0, emoji: item.emoji, revenue: 0 };
            itemCounts[item.name].count += item.qty;
            itemCounts[item.name].revenue += item.price * item.qty;
        });
    });
    var sorted = Object.keys(itemCounts).sort(function (a, b) { return itemCounts[b].count - itemCounts[a].count; }).slice(0, 8);

    var popHtml = '';
    if (sorted.length === 0) {
        popHtml = '<p class="empty-state">Order data will appear here.</p>';
    }
    sorted.forEach(function (name, i) {
        var item = itemCounts[name];
        popHtml += '<div class="popular-item">';
        popHtml += '<span class="pop-rank">' + (i + 1) + '</span>';
        popHtml += '<span class="pop-emoji">' + (item.emoji || '🍽️') + '</span>';
        popHtml += '<span class="pop-name">' + name + '</span>';
        popHtml += '<span class="pop-count">' + item.count + ' sold</span>';
        popHtml += '<span class="pop-revenue">' + DineFlow.formatPrice(item.revenue) + '</span>';
        popHtml += '</div>';
    });
    document.getElementById('popular-items').innerHTML = popHtml;
}

function refreshOrders() {
    var orders = DineFlow.getOrders();
    var buckets = { 'new': [], 'preparing': [], 'ready': [], 'served': [] };

    orders.forEach(function (o) {
        if (buckets[o.status]) buckets[o.status].push(o);
    });

    ['new', 'preparing', 'ready', 'served'].forEach(function (status) {
        var containerId = 'orders-' + (status === 'new' ? 'new' : status);
        var container = document.getElementById(containerId);
        if (!container) return;

        var countEl = document.getElementById(status === 'new' ? 'new-count' : status + '-count');
        if (countEl) countEl.textContent = buckets[status].length;

        var html = '';
        if (buckets[status].length === 0) {
            html = '<div class="order-empty">No orders</div>';
        }
        buckets[status].forEach(function (o) {
            html += '<div class="order-card">';
            html += '<div class="oc-header">';
            html += '<strong>#' + o.id + '</strong>';
            html += '<span class="oc-table">Table ' + o.table + '</span>';
            html += '</div>';
            html += '<div class="oc-time">' + DineFlow.formatTime(o.timestamp) + ' &middot; ' + DineFlow.timeAgo(o.timestamp) + '</div>';
            html += '<div class="oc-items">';
            (o.items || []).forEach(function (item) {
                html += '<div class="oc-item">';
                html += '<span>' + (item.emoji || '') + ' ' + item.name + '</span>';
                html += '<span>&times;' + item.qty + '</span>';
                html += '</div>';
            });
            html += '</div>';
            if (o.notes) {
                html += '<div class="oc-notes">Note: ' + escapeHtml(o.notes) + '</div>';
            }
            html += '<div class="oc-total">Total: ' + DineFlow.formatPrice(o.total) + '</div>';
            html += '<div class="oc-actions">';

            if (status === 'new') {
                html += '<button class="btn btn-sm btn-primary" onclick="moveOrder(\'' + o.id + '\', \'preparing\')">Start Preparing</button>';
            } else if (status === 'preparing') {
                html += '<button class="btn btn-sm btn-primary" onclick="moveOrder(\'' + o.id + '\', \'ready\')">Mark Ready</button>';
            } else if (status === 'ready') {
                html += '<button class="btn btn-sm btn-primary" onclick="moveOrder(\'' + o.id + '\', \'served\')">Mark Served</button>';
            }

            html += '</div></div>';
        });
        container.innerHTML = html;
    });
}

function moveOrder(orderId, newStatus) {
    DineFlow.updateOrderStatus(orderId, newStatus);
    refreshOrders();
    refreshDashboard();
    showToast('Order #' + orderId + ' moved to ' + newStatus);
}

function refreshMenu() {
    var menu = DineFlow.getMenu();
    var container = document.getElementById('admin-menu-list');

    var grouped = {};
    menu.forEach(function (item) {
        if (!grouped[item.category]) grouped[item.category] = [];
        grouped[item.category].push(item);
    });

    var html = '';
    DineFlow.categoryOrder.forEach(function (cat) {
        if (!grouped[cat]) return;
        var label = DineFlow.categoryLabels[cat] || cat;
        html += '<div class="admin-category">';
        html += '<h3 class="admin-cat-title">' + label + ' (' + grouped[cat].length + ')</h3>';
        html += '<div class="admin-items-grid">';

        grouped[cat].forEach(function (item) {
            var avClass = item.available ? '' : ' unavailable';
            html += '<div class="admin-item-card' + avClass + '">';
            html += '<div class="ai-emoji">' + (item.emoji || '🍽️') + '</div>';
            html += '<div class="ai-info">';
            html += '<strong>' + escapeHtml(item.name) + '</strong>';
            html += '<span class="ai-price">' + DineFlow.formatPrice(item.price) + '</span>';
            if (!item.available) html += '<span class="ai-unavailable">Unavailable</span>';
            html += '</div>';
            html += '<div class="ai-actions">';
            html += '<button class="btn-icon" onclick="editMenuItem(' + item.id + ')" title="Edit">&#9998;</button>';
            html += '<button class="btn-icon" onclick="toggleAvailability(' + item.id + ')" title="Toggle">' + (item.available ? '&#128994;' : '&#128308;') + '</button>';
            html += '<button class="btn-icon danger" onclick="deleteMenuItem(' + item.id + ')" title="Delete">&#128465;</button>';
            html += '</div></div>';
        });

        html += '</div></div>';
    });

    if (html === '') html = '<p class="empty-state">No menu items yet. Click "+ Add Item" to start building your menu.</p>';
    container.innerHTML = html;
}

function openMenuModal(itemId) {
    document.getElementById('menu-modal').style.display = 'flex';
    document.getElementById('menu-modal-title').textContent = itemId ? 'Edit Menu Item' : 'Add Menu Item';
    document.getElementById('item-edit-id').value = itemId || '';

    if (itemId) {
        var menu = DineFlow.getMenu();
        var item = menu.find(function (m) { return m.id === itemId; });
        if (item) {
            document.getElementById('item-name').value = item.name;
            document.getElementById('item-category').value = item.category;
            document.getElementById('item-description').value = item.description || '';
            document.getElementById('item-price').value = item.price;
            document.getElementById('item-emoji').value = item.emoji || '';
            document.getElementById('item-available').checked = item.available;
            document.getElementById('item-popular').checked = item.popular || false;
            document.getElementById('item-veg').checked = item.veg || false;
        }
    } else {
        document.getElementById('menu-item-form').reset();
        document.getElementById('item-available').checked = true;
    }
}

function closeMenuModal() {
    document.getElementById('menu-modal').style.display = 'none';
    document.getElementById('menu-item-form').reset();
}

function saveMenuItem(e) {
    e.preventDefault();
    var menu = DineFlow.getMenu();
    var editId = document.getElementById('item-edit-id').value;

    var itemData = {
        name: document.getElementById('item-name').value,
        category: document.getElementById('item-category').value,
        description: document.getElementById('item-description').value,
        price: parseFloat(document.getElementById('item-price').value),
        emoji: document.getElementById('item-emoji').value || '🍽️',
        available: document.getElementById('item-available').checked,
        popular: document.getElementById('item-popular').checked,
        veg: document.getElementById('item-veg').checked
    };

    if (editId) {
        var id = parseInt(editId);
        for (var i = 0; i < menu.length; i++) {
            if (menu[i].id === id) {
                menu[i] = Object.assign(menu[i], itemData);
                break;
            }
        }
        showToast('Item updated!');
    } else {
        itemData.id = DineFlow.getNextMenuId();
        menu.push(itemData);
        showToast('Item added!');
    }

    DineFlow.saveMenu(menu);
    closeMenuModal();
    refreshMenu();
    refreshDashboard();
}

function editMenuItem(id) {
    openMenuModal(id);
}

function toggleAvailability(id) {
    var menu = DineFlow.getMenu();
    for (var i = 0; i < menu.length; i++) {
        if (menu[i].id === id) {
            menu[i].available = !menu[i].available;
            showToast(menu[i].name + ' is now ' + (menu[i].available ? 'available' : 'unavailable'));
            break;
        }
    }
    DineFlow.saveMenu(menu);
    refreshMenu();
}

function deleteMenuItem(id) {
    if (!confirm('Delete this menu item?')) return;
    var menu = DineFlow.getMenu().filter(function (m) { return m.id !== id; });
    DineFlow.saveMenu(menu);
    refreshMenu();
    refreshDashboard();
    showToast('Item deleted');
}

function refreshTables() {
    var tables = DineFlow.getTables();
    var container = document.getElementById('tables-grid');
    var baseUrl = window.location.origin + window.location.pathname.replace('admin.html', 'order.html');

    var html = '';
    tables.forEach(function (table) {
        var url = baseUrl + '?table=' + table.id;
        var qrUrl = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(url);

        html += '<div class="table-card">';
        html += '<div class="tc-header"><strong>' + table.name + '</strong></div>';
        html += '<a href="' + url + '" target="_blank" class="tc-qr">';
        html += '<img src="' + qrUrl + '" alt="QR Code for ' + table.name + '" width="160" height="160">';
        html += '</a>';
        html += '<div class="tc-actions">';
        html += '<a href="' + url + '" target="_blank" class="btn btn-sm btn-outline">Preview</a>';
        html += '<button class="btn btn-sm btn-primary" onclick="printQR(\'' + table.name + '\', \'' + qrUrl + '\')">Print</button>';
        html += '</div></div>';
    });
    container.innerHTML = html;
}

function addTable() {
    var tables = DineFlow.getTables();
    var nextId = tables.length > 0 ? Math.max.apply(null, tables.map(function (t) { return t.id; })) + 1 : 1;
    tables.push({ id: nextId, name: 'Table ' + nextId, active: true });
    DineFlow.saveTables(tables);
    refreshTables();
    showToast('Table ' + nextId + ' added');
}

function printQR(name, qrUrl) {
    var w = window.open('', '_blank');
    w.document.write('<html><head><title>QR - ' + name + '</title>');
    w.document.write('<style>body{font-family:Arial;text-align:center;padding:40px}h1{font-size:32px}p{font-size:18px;color:#666}img{margin:20px}</style>');
    w.document.write('</head><body>');
    w.document.write('<h1>' + name + '</h1>');
    w.document.write('<img src="' + qrUrl + '" width="300" height="300">');
    w.document.write('<p>Scan to view menu & order</p>');
    w.document.write('<p style="font-size:14px;color:#999">Powered by DineFlow</p>');
    w.document.write('<script>setTimeout(function(){window.print()},500)<\/script>');
    w.document.write('</body></html>');
    w.document.close();
}

function showToast(message) {
    var toast = document.getElementById('toast');
    document.getElementById('toast-message').textContent = message;
    toast.style.display = 'block';
    setTimeout(function () { toast.style.display = 'none'; }, 3000);
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str || ''));
    return div.innerHTML;
}
