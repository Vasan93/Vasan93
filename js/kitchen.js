document.addEventListener('DOMContentLoaded', function () {
    updateTime();
    setInterval(updateTime, 1000);
    refreshKitchen();
    setInterval(refreshKitchen, 3000);
});

function updateTime() {
    var now = new Date();
    document.getElementById('kitchen-time').textContent = now.toLocaleTimeString('en-US', {
        hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
}

function refreshKitchen() {
    var orders = DineFlow.getOrders();
    var buckets = { 'new': [], 'preparing': [], 'ready': [] };

    orders.forEach(function (o) {
        if (buckets[o.status]) buckets[o.status].push(o);
    });

    renderColumn('k-orders-new', buckets['new'], 'new', 'k-new-count');
    renderColumn('k-orders-prep', buckets['preparing'], 'preparing', 'k-prep-count');
    renderColumn('k-orders-ready', buckets['ready'], 'ready', 'k-ready-count');
}

function renderColumn(containerId, orders, status, countId) {
    var container = document.getElementById(containerId);
    document.getElementById(countId).textContent = orders.length;

    if (orders.length === 0) {
        container.innerHTML = '<div class="k-empty">No orders</div>';
        return;
    }

    var html = '';
    orders.forEach(function (o) {
        var elapsed = getElapsed(o.timestamp);
        var urgentClass = elapsed > 15 ? ' urgent' : elapsed > 10 ? ' warning' : '';

        html += '<div class="k-order-card' + urgentClass + '">';
        html += '<div class="k-header">';
        html += '<span class="k-order-id">#' + o.id + '</span>';
        html += '<span class="k-table">TABLE ' + o.table + '</span>';
        html += '</div>';
        html += '<div class="k-time">' + DineFlow.formatTime(o.timestamp) + ' &middot; ' + elapsed + ' min ago</div>';
        html += '<div class="k-items">';
        (o.items || []).forEach(function (item) {
            html += '<div class="k-item">';
            html += '<span class="k-qty">' + item.qty + 'x</span>';
            html += '<span class="k-name">' + (item.emoji || '') + ' ' + item.name + '</span>';
            html += '</div>';
        });
        html += '</div>';
        if (o.notes) {
            html += '<div class="k-notes">&#9888; ' + escapeHtml(o.notes) + '</div>';
        }
        html += '<div class="k-actions">';
        if (status === 'new') {
            html += '<button class="k-btn preparing" onclick="kitchenMove(\'' + o.id + '\', \'preparing\')">START PREPARING</button>';
        } else if (status === 'preparing') {
            html += '<button class="k-btn ready" onclick="kitchenMove(\'' + o.id + '\', \'ready\')">MARK READY</button>';
        } else if (status === 'ready') {
            html += '<button class="k-btn served" onclick="kitchenMove(\'' + o.id + '\', \'served\')">SERVED</button>';
        }
        html += '</div></div>';
    });

    container.innerHTML = html;
}

function kitchenMove(orderId, newStatus) {
    DineFlow.updateOrderStatus(orderId, newStatus);
    refreshKitchen();
}

function getElapsed(timestamp) {
    return Math.floor((new Date() - new Date(timestamp)) / 60000);
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str || ''));
    return div.innerHTML;
}
