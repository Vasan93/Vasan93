var DineFlow = (function () {
    var MENU_KEY = 'dineflow_menu';
    var ORDERS_KEY = 'dineflow_orders';
    var TABLES_KEY = 'dineflow_tables';

    var defaultMenu = [
        { id: 1, name: 'Bruschetta', category: 'starters', description: 'Toasted bread topped with fresh tomatoes, basil, and garlic', price: 8.99, emoji: '🍞', available: true, popular: true, veg: true },
        { id: 2, name: 'Calamari Fritti', category: 'starters', description: 'Crispy fried squid rings with marinara dipping sauce', price: 11.99, emoji: '🦑', available: true, popular: false, veg: false },
        { id: 3, name: 'Soup of the Day', category: 'starters', description: 'Chef\'s daily selection served with artisan bread', price: 7.49, emoji: '🍲', available: true, popular: false, veg: true },
        { id: 4, name: 'Chicken Wings', category: 'starters', description: 'Crispy wings tossed in buffalo sauce with ranch dip', price: 12.99, emoji: '🍗', available: true, popular: true, veg: false },

        { id: 5, name: 'Grilled Salmon', category: 'mains', description: 'Atlantic salmon with lemon butter, asparagus, and mashed potatoes', price: 24.99, emoji: '🐟', available: true, popular: true, veg: false },
        { id: 6, name: 'Ribeye Steak', category: 'mains', description: '12oz USDA Choice ribeye with roasted vegetables and herb butter', price: 32.99, emoji: '🥩', available: true, popular: true, veg: false },
        { id: 7, name: 'Chicken Parmesan', category: 'mains', description: 'Breaded chicken breast with marinara, mozzarella, and spaghetti', price: 19.99, emoji: '🍗', available: true, popular: false, veg: false },
        { id: 8, name: 'Vegetable Risotto', category: 'mains', description: 'Creamy arborio rice with seasonal vegetables and parmesan', price: 17.99, emoji: '🍚', available: true, popular: false, veg: true },

        { id: 9, name: 'Margherita Pizza', category: 'pizza', description: 'San Marzano tomato sauce, fresh mozzarella, and basil', price: 14.99, emoji: '🍕', available: true, popular: true, veg: true },
        { id: 10, name: 'Pepperoni Pizza', category: 'pizza', description: 'Classic pepperoni with mozzarella and our signature sauce', price: 16.99, emoji: '🍕', available: true, popular: true, veg: false },
        { id: 11, name: 'BBQ Chicken Pizza', category: 'pizza', description: 'Grilled chicken, red onion, cilantro, and smoky BBQ sauce', price: 17.99, emoji: '🍕', available: true, popular: false, veg: false },

        { id: 12, name: 'Classic Burger', category: 'burgers', description: 'Angus beef patty with lettuce, tomato, pickles, and special sauce', price: 15.99, emoji: '🍔', available: true, popular: true, veg: false },
        { id: 13, name: 'Mushroom Swiss Burger', category: 'burgers', description: 'Sautéed mushrooms and melted Swiss on a brioche bun', price: 17.49, emoji: '🍔', available: true, popular: false, veg: false },
        { id: 14, name: 'Veggie Burger', category: 'burgers', description: 'House-made plant-based patty with avocado and sprouts', price: 14.99, emoji: '🍔', available: true, popular: false, veg: true },

        { id: 15, name: 'Spaghetti Bolognese', category: 'pasta', description: 'Slow-cooked meat sauce over al dente spaghetti', price: 16.99, emoji: '🍝', available: true, popular: true, veg: false },
        { id: 16, name: 'Fettuccine Alfredo', category: 'pasta', description: 'Creamy parmesan sauce with fettuccine pasta', price: 15.99, emoji: '🍝', available: true, popular: false, veg: true },
        { id: 17, name: 'Penne Arrabbiata', category: 'pasta', description: 'Spicy tomato sauce with garlic and red chili flakes', price: 14.49, emoji: '🍝', available: true, popular: false, veg: true },

        { id: 18, name: 'Caesar Salad', category: 'salads', description: 'Romaine lettuce, croutons, parmesan, and Caesar dressing', price: 11.99, emoji: '🥗', available: true, popular: true, veg: true },
        { id: 19, name: 'Greek Salad', category: 'salads', description: 'Cucumber, tomato, olives, feta cheese, and olive oil', price: 10.99, emoji: '🥗', available: true, popular: false, veg: true },

        { id: 20, name: 'French Fries', category: 'sides', description: 'Crispy golden fries with sea salt', price: 5.99, emoji: '🍟', available: true, popular: true, veg: true },
        { id: 21, name: 'Garlic Bread', category: 'sides', description: 'Toasted with garlic butter and herbs', price: 4.99, emoji: '🧄', available: true, popular: false, veg: true },
        { id: 22, name: 'Onion Rings', category: 'sides', description: 'Beer-battered and deep fried with chipotle mayo', price: 6.99, emoji: '🧅', available: true, popular: false, veg: true },

        { id: 23, name: 'Tiramisu', category: 'desserts', description: 'Classic Italian dessert with espresso-soaked ladyfingers', price: 9.99, emoji: '🍰', available: true, popular: true, veg: true },
        { id: 24, name: 'Chocolate Lava Cake', category: 'desserts', description: 'Warm chocolate cake with molten center and vanilla ice cream', price: 10.99, emoji: '🍫', available: true, popular: true, veg: true },
        { id: 25, name: 'Cheesecake', category: 'desserts', description: 'New York style with strawberry compote', price: 9.49, emoji: '🍰', available: true, popular: false, veg: true },

        { id: 26, name: 'Coca-Cola', category: 'drinks', description: 'Classic 330ml', price: 2.99, emoji: '🥤', available: true, popular: false, veg: true },
        { id: 27, name: 'Fresh Lemonade', category: 'drinks', description: 'Freshly squeezed with mint', price: 4.99, emoji: '🍋', available: true, popular: true, veg: true },
        { id: 28, name: 'Iced Tea', category: 'drinks', description: 'Peach or lemon flavored', price: 3.99, emoji: '🧊', available: true, popular: false, veg: true },
        { id: 29, name: 'Espresso', category: 'drinks', description: 'Double shot Italian espresso', price: 3.49, emoji: '☕', available: true, popular: false, veg: true },
        { id: 30, name: 'Mango Smoothie', category: 'drinks', description: 'Fresh mango blended with yogurt and honey', price: 6.99, emoji: '🥭', available: true, popular: true, veg: true }
    ];

    var categoryLabels = {
        'starters': 'Starters',
        'mains': 'Main Course',
        'pizza': 'Pizza',
        'burgers': 'Burgers',
        'pasta': 'Pasta',
        'salads': 'Salads',
        'sides': 'Sides',
        'desserts': 'Desserts',
        'drinks': 'Drinks',
        'specials': "Chef's Specials"
    };

    var categoryOrder = ['starters', 'mains', 'pizza', 'burgers', 'pasta', 'salads', 'sides', 'desserts', 'drinks', 'specials'];

    function getMenu() {
        var stored = localStorage.getItem(MENU_KEY);
        if (stored) return JSON.parse(stored);
        localStorage.setItem(MENU_KEY, JSON.stringify(defaultMenu));
        return defaultMenu;
    }

    function saveMenu(menu) {
        localStorage.setItem(MENU_KEY, JSON.stringify(menu));
    }

    function getOrders() {
        var stored = localStorage.getItem(ORDERS_KEY);
        return stored ? JSON.parse(stored) : [];
    }

    function saveOrders(orders) {
        localStorage.setItem(ORDERS_KEY, JSON.stringify(orders));
    }

    function addOrder(order) {
        var orders = getOrders();
        order.id = Date.now().toString(36).toUpperCase();
        order.timestamp = new Date().toISOString();
        order.status = 'new';
        orders.unshift(order);
        saveOrders(orders);
        return order;
    }

    function updateOrderStatus(orderId, status) {
        var orders = getOrders();
        for (var i = 0; i < orders.length; i++) {
            if (orders[i].id === orderId) {
                orders[i].status = status;
                break;
            }
        }
        saveOrders(orders);
    }

    function getTables() {
        var stored = localStorage.getItem(TABLES_KEY);
        if (stored) return JSON.parse(stored);
        var tables = [];
        for (var i = 1; i <= 12; i++) {
            tables.push({ id: i, name: 'Table ' + i, active: true });
        }
        localStorage.setItem(TABLES_KEY, JSON.stringify(tables));
        return tables;
    }

    function saveTables(tables) {
        localStorage.setItem(TABLES_KEY, JSON.stringify(tables));
    }

    function getNextMenuId() {
        var menu = getMenu();
        var maxId = 0;
        for (var i = 0; i < menu.length; i++) {
            if (menu[i].id > maxId) maxId = menu[i].id;
        }
        return maxId + 1;
    }

    function formatPrice(price) {
        return '$' + parseFloat(price).toFixed(2);
    }

    function formatTime(isoString) {
        var d = new Date(isoString);
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }

    function timeAgo(isoString) {
        var now = new Date();
        var then = new Date(isoString);
        var diff = Math.floor((now - then) / 60000);
        if (diff < 1) return 'Just now';
        if (diff < 60) return diff + ' min ago';
        return Math.floor(diff / 60) + 'h ago';
    }

    return {
        getMenu: getMenu,
        saveMenu: saveMenu,
        getOrders: getOrders,
        saveOrders: saveOrders,
        addOrder: addOrder,
        updateOrderStatus: updateOrderStatus,
        getTables: getTables,
        saveTables: saveTables,
        getNextMenuId: getNextMenuId,
        formatPrice: formatPrice,
        formatTime: formatTime,
        timeAgo: timeAgo,
        categoryLabels: categoryLabels,
        categoryOrder: categoryOrder
    };
})();
