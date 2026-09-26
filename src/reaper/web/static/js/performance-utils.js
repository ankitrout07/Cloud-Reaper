/**
 * Performance Utilities for Cloud-Reaper
 * Includes debouncing, throttling, and other performance optimization helpers
 */

// Debounce function - delays function execution until after wait milliseconds have elapsed
// since the last time the debounced function was invoked
function debounce(func, wait = 300, immediate = false) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            timeout = null;
            if (!immediate) func.apply(this, args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func.apply(this, args);
    };
}

// Throttle function - ensures function is called at most once every limit milliseconds
function throttle(func, limit = 100) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Debounced search input handler
function setupDebouncedSearch(inputSelector, searchCallback, delay = 300) {
    const searchInput = document.querySelector(inputSelector);
    if (!searchInput || searchInput.dataset.debouncedBound === 'true') return;
    searchInput.dataset.debouncedBound = 'true';
    
    const debouncedSearch = debounce((query) => {
        searchCallback(query);
    }, delay);
    
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        debouncedSearch(query);
    });
    
    // Clear search on escape key
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            searchInput.value = '';
            debouncedSearch('');
        }
    });
}

// Auto-save with debouncing
function setupAutoSave(formSelector, saveCallback, delay = 1000) {
    const form = document.querySelector(formSelector);
    if (!form || form.dataset.autoSaveBound === 'true') return;
    form.dataset.autoSaveBound = 'true';
    
    const debouncedSave = debounce(() => {
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        saveCallback(data);
    }, delay);
    
    // Listen for input changes on all form elements
    form.addEventListener('input', debouncedSave);
    form.addEventListener('change', debouncedSave);
    
    // Save on form submission
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        saveCallback(data);
    });
}

// Lazy load images
function lazyLoadImages() {
    const images = document.querySelectorAll('img[data-src]');
    
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.removeAttribute('data-src');
                    observer.unobserve(img);
                }
            });
        });
        
        images.forEach(img => imageObserver.observe(img));
    } else {
        // Fallback for browsers without IntersectionObserver
        images.forEach(img => {
            img.src = img.dataset.src;
            img.removeAttribute('data-src');
        });
    }
}

// Request animation frame throttle for smooth animations
function rafThrottle(callback) {
    let ticking = false;
    return function(...args) {
        if (!ticking) {
            requestAnimationFrame(() => {
                callback.apply(this, args);
                ticking = false;
            });
            ticking = true;
        }
    };
}

// Performance monitoring
function measurePerformance(name, fn) {
    const start = performance.now();
    const result = fn();
    const end = performance.now();
    console.log(`${name} took ${(end - start).toFixed(2)}ms`);
    return result;
}

// Async performance monitoring
async function measureAsyncPerformance(name, fn) {
    const start = performance.now();
    const result = await fn();
    const end = performance.now();
    console.log(`${name} took ${(end - start).toFixed(2)}ms`);
    return result;
}

// Initialize performance utilities when DOM is ready or swapped via HTMX
function initPerformanceUtils() {
    // Initialize lazy loading for images
    lazyLoadImages();
    
    // Setup debounced search for resource inventory
    setupDebouncedSearch(
        '#resource-search',
        (query) => {
            // Trigger HTMX search with debounced query
            const searchInput = document.querySelector('#resource-search');
            if (searchInput && typeof htmx !== 'undefined') {
                htmx.trigger(searchInput, 'search', { query });
            }
        },
        300
    );
    
    // Setup auto-save for settings forms
    setupAutoSave(
        '#settings-form',
        (data) => {
            // Save settings via API
            fetch('/api/settings/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            }).then(response => {
                if (response.ok) {
                    console.log('Settings auto-saved');
                }
            }).catch(err => console.warn('Auto-save settings failed:', err));
        },
        1000
    );
    
    // Setup auto-save for vault configuration
    setupAutoSave(
        '#vault-config-form',
        (data) => {
            // Save vault config via API
            fetch('/api/vault/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            }).then(response => {
                if (response.ok) {
                    console.log('Vault config auto-saved');
                }
            }).catch(err => console.warn('Auto-save vault failed:', err));
        },
        1000
    );
}

document.addEventListener('DOMContentLoaded', initPerformanceUtils);
document.addEventListener('htmx:afterSwap', initPerformanceUtils);

// Auto-export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        debounce,
        throttle,
        setupDebouncedSearch,
        setupAutoSave,
        lazyLoadImages,
        rafThrottle,
        measurePerformance,
        measureAsyncPerformance
    };
}
