/**
 * Service Worker for Cloud-Reaper
 * Provides offline support and caching for better performance
 */

const CACHE_NAME = 'cloud-reaper-v1';
const STATIC_CACHE = 'cloud-reaper-static-v1';
const API_CACHE = 'cloud-reaper-api-v1';

// Static assets to cache immediately
const STATIC_ASSETS = [
    '/',
    '/static/css/professional-theme.css',
    '/static/css/components.css',
    '/static/css/main.css',
    '/static/css/professional-dark.css',
    '/static/js/app_state.js',
    '/static/js/theme.js',
    '/static/js/setup.js',
    '/static/js/ui-interactions.js',
    '/static/js/performance-utils.js',
    '/static/assets/favicon.png'
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Installing...');
    
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => {
                console.log('[Service Worker] Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => {
                return self.skipWaiting();
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activating...');
    
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames.map((cacheName) => {
                        if (cacheName !== STATIC_CACHE && cacheName !== API_CACHE) {
                            console.log('[Service Worker] Deleting old cache:', cacheName);
                            return caches.delete(cacheName);
                        }
                    })
                );
            })
            .then(() => {
                return self.clients.claim();
            })
    );
});

// Fetch event - serve from cache with network fallback
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }
    
    // Skip cross-origin requests
    if (url.origin !== location.origin) {
        return;
    }

    // Never cache HTMX partial fragment requests (prevent cache poisoning of full pages)
    if (event.request.headers.get('HX-Request')) {
        event.respondWith(fetch(event.request));
        return;
    }
    
    // Handle static assets - cache first, network fallback
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(event.request)
                .then((response) => {
                    if (response) {
                        return response;
                    }
                    return fetch(event.request).then((response) => {
                        // Cache successful responses
                        if (response.status === 200) {
                            const responseClone = response.clone();
                            caches.open(STATIC_CACHE).then((cache) => {
                                cache.put(event.request, responseClone);
                            });
                        }
                        return response;
                    });
                })
        );
        return;
    }
    
    // Handle API requests - network first, cache fallback
    if (url.pathname.startsWith('/api/')) {
        // Only cache GET requests for data that doesn't change frequently
        if (url.pathname.includes('/api/metrics') || 
            url.pathname.includes('/api/catalog') ||
            url.pathname.includes('/api/prices')) {
            event.respondWith(
                fetch(event.request)
                    .then((response) => {
                        // Cache successful responses
                        if (response.status === 200) {
                            const responseClone = response.clone();
                            caches.open(API_CACHE).then((cache) => {
                                cache.put(event.request, responseClone);
                            });
                        }
                        return response;
                    })
                    .catch(() => {
                        // Return cached version if network fails
                        return caches.match(event.request);
                    })
            );
        } else {
            // For other API requests, don't cache
            event.respondWith(fetch(event.request));
        }
        return;
    }
    
    // Handle HTML pages - network first, cache fallback
    if (url.pathname.endsWith('.html') || url.pathname === '/') {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                    return response;
                })
                .catch(() => {
                    return caches.match(event.request);
                })
        );
        return;
    }
    
    // Default: network first, cache fallback
    event.respondWith(
        fetch(event.request)
            .then((response) => {
                const responseClone = response.clone();
                caches.open(CACHE_NAME).then((cache) => {
                    cache.put(event.request, responseClone);
                });
                return response;
            })
            .catch(() => {
                return caches.match(event.request);
            })
    );
});

// Background sync for offline actions
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-settings') {
        event.waitUntil(syncSettings());
    }
});

// Push notifications
self.addEventListener('push', (event) => {
    const options = {
        body: event.data ? event.data.text() : 'Cloud-Reaper notification',
        icon: '/static/assets/favicon.png',
        badge: '/static/assets/favicon.png',
        vibrate: [100, 50, 100],
        data: {
            dateOfArrival: Date.now(),
            primaryKey: 1
        }
    };
    
    event.waitUntil(
        self.registration.showNotification('Cloud-Reaper', options)
    );
});

// Handle notification clicks
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    event.waitUntil(
        clients.openWindow('/')
    );
});

// Sync settings function
function syncSettings() {
    return fetch('/api/settings/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    }).then((response) => {
        console.log('[Service Worker] Settings synced');
    }).catch((error) => {
        console.error('[Service Worker] Settings sync failed:', error);
    });
}

// Cache cleanup function
function cleanupCache() {
    return caches.keys().then((cacheNames) => {
        return Promise.all(
            cacheNames.map((cacheName) => {
                if (cacheName !== STATIC_CACHE && cacheName !== API_CACHE && cacheName !== CACHE_NAME) {
                    return caches.delete(cacheName);
                }
            })
        );
    });
}
