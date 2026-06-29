var cart = [];
var currentModalItem = null;
var modalQty = 1;

document.addEventListener('DOMContentLoaded', function () {
    var params = new URLSearchParams(window.location.search);
    var tableNum = params.get('table') || '1';
    document.getElementById('table-number').textContent = tableNum;
    loadMenu();
});

function loadMenu() {
    var menu = DineFlow.getMenu().filter(function (item) { return item.available; });
    var container = document.getElementById('menu-container');
    var categoryNav = document.getElementById('category-nav');

    var grouped = {};
    menu.forEach(function (item) {
        if (!grouped[item.category]) grouped[item.category] = [];
        grouped[item.category].push(item);
    });

    var navHtml = '<button class="cat-btn active" onclick="scrollToCategory(\'all\', this)">All</button>';
    var menuHtml = '';

    DineFlow.categoryOrder.forEach(function (cat) {
        if (!grouped[cat]) return;
        var label = DineFlow.categoryLabels[cat] || cat;
        navHtml += '<button class="cat-btn" onclick="scrollToCategory(\'' + cat + '\', this)">' + label + '</button>';

        menuHtml += '<section class="menu-section" id="cat-' + cat + '">';
        menuHtml += '<h2 class="menu-section-title">' + label + '</h2>';
        menuHtml += '<div class="menu-grid">';

        grouped[cat].forEach(function (item) {
            var popularTag = item.popular ? '<span class="popular-tag">Popular</span>' : '';
            var vegTag = item.veg ? '<span class="veg-tag">VEG</span>' : '';
            menuHtml += '<div class="menu-card" onclick="openItemModal(' + item.id + ')">';
            menuHtml += '<div class="menu-card-img">' + (item.emoji || '🍽️') + '</div>';
            menuHtml += '<div class="menu-card-body">';
            menuHtml += '<div class="menu-card-tags">' + popularTag + vegTag + '</div>';
            menuHtml += '<h3>' + escapeHtml(item.name) + '</h3>';
            menuHtml += '<p class="menu-card-desc">' + escapeHtml(item.description || '') + '</p>';
            menuHtml += '<div class="menu-card-footer">';
            menuHtml += '<span class="menu-card-price">' + DineFlow.formatPrice(item.price) + '</span>';
            menuHtml += '<button class="add-btn" onclick="event.stopPropagation(); quickAdd(' + item.id + ')">+</button>';
            menuHtml += '</div></div></div>';
        });

        menuHtml += '</div></section>';
    });

    categoryNav.innerHTML = navHtml;
    container.innerHTML = menuHtml;
}

function scrollToCategory(cat, btn) {
    document.querySelectorAll('.cat-btn').forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');

    if (cat === 'all') {
        document.getElementById('menu-container').scrollTo({ top: 0, behavior: 'smooth' });
        return;
    }
    var el = document.getElementById('cat-' + cat);
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function openItemModal(itemId) {
    var menu = DineFlow.getMenu();
    var item = menu.find(function (m) { return m.id === itemId; });
    if (!item) return;

    currentModalItem = item;
    modalQty = 1;

    document.getElementById('modal-img').textContent = item.emoji || '🍽️';
    document.getElementById('modal-name').textContent = item.name;
    document.getElementById('modal-desc').textContent = item.description || '';
    document.getElementById('modal-price').textContent = DineFlow.formatPrice(item.price);
    document.getElementById('modal-qty').textContent = '1';
    document.getElementById('modal-add-btn').textContent = 'Add to Order - ' + DineFlow.formatPrice(item.price);
    document.getElementById('item-modal').style.display = 'flex';
}

function closeItemModal(e) {
    if (e && e.target !== document.getElementById('item-modal')) return;
    document.getElementById('item-modal').style.display = 'none';
    currentModalItem = null;
}

function changeModalQty(delta) {
    modalQty = Math.max(1, modalQty + delta);
    document.getElementById('modal-qty').textContent = modalQty;
    if (currentModalItem) {
        var total = currentModalItem.price * modalQty;
        document.getElementById('modal-add-btn').textContent = 'Add to Order - ' + DineFlow.formatPrice(total);
    }
}

function addFromModal() {
    if (!currentModalItem) return;
    addToCart(currentModalItem.id, modalQty);
    document.getElementById('item-modal').style.display = 'none';
    currentModalItem = null;
}

function quickAdd(itemId) {
    addToCart(itemId, 1);
}

function addToCart(itemId, qty) {
    var existing = cart.find(function (c) { return c.itemId === itemId; });
    if (existing) {
        existing.qty += qty;
    } else {
        var menu = DineFlow.getMenu();
        var item = menu.find(function (m) { return m.id === itemId; });
        if (!item) return;
        cart.push({ itemId: itemId, name: item.name, price: item.price, qty: qty, emoji: item.emoji });
    }
    updateCartUI();
    pulseCartBtn();
}

function removeFromCart(itemId) {
    cart = cart.filter(function (c) { return c.itemId !== itemId; });
    updateCartUI();
}

function changeCartQty(itemId, delta) {
    var item = cart.find(function (c) { return c.itemId === itemId; });
    if (!item) return;
    item.qty += delta;
    if (item.qty <= 0) {
        removeFromCart(itemId);
        return;
    }
    updateCartUI();
}

function updateCartUI() {
    var totalItems = cart.reduce(function (sum, c) { return sum + c.qty; }, 0);
    document.getElementById('cart-count').textContent = totalItems;

    var cartItemsEl = document.getElementById('cart-items');
    var cartFooter = document.getElementById('cart-footer');
    var cartEmpty = document.getElementById('cart-empty');

    if (cart.length === 0) {
        cartEmpty.style.display = 'block';
        cartFooter.style.display = 'none';
        cartItemsEl.innerHTML = '';
        cartItemsEl.appendChild(cartEmpty);
        return;
    }

    cartEmpty.style.display = 'none';
    cartFooter.style.display = 'block';

    var html = '';
    var subtotal = 0;
    cart.forEach(function (item) {
        var itemTotal = item.price * item.qty;
        subtotal += itemTotal;
        html += '<div class="cart-item">';
        html += '<div class="cart-item-info">';
        html += '<span class="cart-item-emoji">' + (item.emoji || '🍽️') + '</span>';
        html += '<div><strong>' + escapeHtml(item.name) + '</strong>';
        html += '<br><span class="cart-item-price">' + DineFlow.formatPrice(item.price) + ' each</span></div>';
        html += '</div>';
        html += '<div class="cart-item-controls">';
        html += '<button class="qty-btn-sm" onclick="changeCartQty(' + item.itemId + ', -1)">-</button>';
        html += '<span class="cart-item-qty">' + item.qty + '</span>';
        html += '<button class="qty-btn-sm" onclick="changeCartQty(' + item.itemId + ', 1)">+</button>';
        html += '<span class="cart-item-total">' + DineFlow.formatPrice(itemTotal) + '</span>';
        html += '</div></div>';
    });

    cartItemsEl.innerHTML = html;

    var tax = subtotal * 0.08;
    var total = subtotal + tax;
    document.getElementById('cart-subtotal').textContent = DineFlow.formatPrice(subtotal);
    document.getElementById('cart-tax').textContent = DineFlow.formatPrice(tax);
    document.getElementById('cart-total').textContent = DineFlow.formatPrice(total);
}

function toggleCart() {
    var overlay = document.getElementById('cart-overlay');
    var drawer = document.getElementById('cart-drawer');
    var isOpen = drawer.classList.contains('open');

    if (isOpen) {
        drawer.classList.remove('open');
        overlay.classList.remove('open');
    } else {
        drawer.classList.add('open');
        overlay.classList.add('open');
    }
}

function pulseCartBtn() {
    var btn = document.getElementById('cart-btn');
    btn.classList.add('pulse');
    setTimeout(function () { btn.classList.remove('pulse'); }, 300);
}

function placeOrder() {
    if (cart.length === 0) return;

    var tableNum = document.getElementById('table-number').textContent;
    var notes = document.getElementById('order-notes').value;
    var subtotal = cart.reduce(function (sum, c) { return sum + c.price * c.qty; }, 0);
    var tax = subtotal * 0.08;

    var order = {
        table: tableNum,
        items: cart.map(function (c) {
            return { itemId: c.itemId, name: c.name, price: c.price, qty: c.qty, emoji: c.emoji };
        }),
        subtotal: subtotal,
        tax: tax,
        total: subtotal + tax,
        notes: notes
    };

    var placed = DineFlow.addOrder(order);

    document.getElementById('order-id').textContent = placed.id;
    document.getElementById('order-success').style.display = 'flex';

    cart = [];
    updateCartUI();
    toggleCart();
    document.getElementById('order-notes').value = '';
}

function closeSuccess() {
    document.getElementById('order-success').style.display = 'none';
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str || ''));
    return div.innerHTML;
}
