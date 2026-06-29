# DineFlow

**QR Code Table Ordering System for Restaurants**

Let your guests order from their phone. DineFlow turns every table into a self-service ordering station with a simple QR code. No app downloads required.

## How It Works

1. Restaurant owner adds their menu in the admin dashboard
2. Print QR codes for each table
3. Guests scan, browse the menu, and place orders from their phone
4. Orders appear instantly on the kitchen display and admin panel

## Pages

| Page | URL | Description |
|------|-----|-------------|
| Landing | `index.html` | Marketing page to sell to restaurants |
| Customer Order | `order.html?table=5` | Mobile ordering (accessed via QR code) |
| Admin Dashboard | `admin.html` | Menu manager, live orders, tables & QR |
| Kitchen Display | `kitchen.html` | Real-time order queue for kitchen staff |

## Features

- **QR Code Ordering** - Unique QR per table, no app download needed
- **30-Item Demo Menu** - 9 categories with emoji icons, VEG/Popular tags
- **Cart & Checkout** - Quantity controls, tax calculation, special instructions
- **Live Orders Board** - Kanban: New > Preparing > Ready > Served
- **Menu Manager** - Add/edit/delete items, toggle availability in real-time
- **Kitchen Display** - Dark-themed, elapsed time tracking, urgency alerts
- **Dashboard Analytics** - Revenue, order count, popular items
- **QR Code Generator** - Auto-generated printable QR codes per table

## Tech Stack

- Pure HTML, CSS, JavaScript (zero dependencies)
- localStorage for MVP data persistence
- No build step, deployable anywhere

## Revenue Model

| Plan | Price | Features |
|------|-------|----------|
| Starter | $29/mo | 10 tables, 50 menu items |
| Professional | $69/mo | Unlimited, online payments, analytics |
| Enterprise | $149/mo | Multi-location, POS integration, API |

## Deploy

Works on GitHub Pages, Netlify, Vercel, or any static host. Just point to the repo.

## Roadmap

- [ ] Backend API (Node.js/Express or Supabase)
- [ ] Stripe payment integration
- [ ] Real-time WebSocket order updates
- [ ] Restaurant owner authentication
- [ ] Multi-language menu support
- [ ] Photo upload for menu items
- [ ] Recurring order / favorites
- [ ] POS system integration
