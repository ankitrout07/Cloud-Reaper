/**
 * Virtual Scrolling Implementation for Large Resource Lists
 * Improves performance by only rendering visible items in the viewport
 */

class VirtualScroll {
    constructor(options) {
        this.container = options.container;
        this.itemHeight = options.itemHeight || 50;
        this.buffer = options.buffer || 5;
        this.items = options.items || [];
        this.renderItem = options.renderItem || this.defaultRenderItem;
        this.totalHeight = this.items.length * this.itemHeight;
        
        this.scrollTop = 0;
        this.visibleStart = 0;
        this.visibleEnd = 0;
        
        this.init();
    }
    
    init() {
        this.container.style.position = 'relative';
        this.container.style.overflow = 'auto';
        this.container.style.height = '100%';
        
        // Create spacer for total height
        this.spacer = document.createElement('div');
        this.spacer.style.height = `${this.totalHeight}px`;
        this.spacer.style.position = 'absolute';
        this.spacer.style.top = '0';
        this.spacer.style.left = '0';
        this.spacer.style.width = '100%';
        this.container.appendChild(this.spacer);
        
        // Create viewport for visible items
        this.viewport = document.createElement('div');
        this.viewport.style.position = 'absolute';
        this.viewport.style.top = '0';
        this.viewport.style.left = '0';
        this.viewport.style.width = '100%';
        this.container.appendChild(this.viewport);
        
        // Bind scroll event
        this.container.addEventListener('scroll', this.handleScroll.bind(this));
        
        // Initial render
        this.updateVisibleRange();
        this.render();
    }
    
    handleScroll() {
        this.scrollTop = this.container.scrollTop;
        this.updateVisibleRange();
        this.render();
    }
    
    updateVisibleRange() {
        const containerHeight = this.container.clientHeight;
        const startIndex = Math.floor(this.scrollTop / this.itemHeight);
        const endIndex = Math.ceil((this.scrollTop + containerHeight) / this.itemHeight);
        
        this.visibleStart = Math.max(0, startIndex - this.buffer);
        this.visibleEnd = Math.min(this.items.length, endIndex + this.buffer);
    }
    
    render() {
        // Clear viewport
        this.viewport.innerHTML = '';
        
        // Set viewport position
        this.viewport.style.transform = `translateY(${this.visibleStart * this.itemHeight}px)`;
        
        // Render visible items
        for (let i = this.visibleStart; i < this.visibleEnd; i++) {
            const item = this.items[i];
            const element = this.renderItem(item, i);
            element.style.height = `${this.itemHeight}px`;
            element.style.position = 'absolute';
            element.style.top = `${(i - this.visibleStart) * this.itemHeight}px`;
            element.style.left = '0';
            element.style.width = '100%';
            this.viewport.appendChild(element);
        }
    }
    
    defaultRenderItem(item, index) {
        const div = document.createElement('div');
        div.textContent = JSON.stringify(item);
        return div;
    }
    
    updateItems(newItems) {
        this.items = newItems;
        this.totalHeight = this.items.length * this.itemHeight;
        this.spacer.style.height = `${this.totalHeight}px`;
        this.updateVisibleRange();
        this.render();
    }
    
    scrollToIndex(index) {
        this.container.scrollTop = index * this.itemHeight;
    }
    
    destroy() {
        this.container.removeEventListener('scroll', this.handleScroll.bind(this));
        this.container.innerHTML = '';
    }
}

// Debounce utility function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Throttle utility function
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Initialize virtual scroll on resource inventory tables
function initVirtualScroll() {
    const resourceTable = document.getElementById('resource-table');
    if (!resourceTable) return;
    
    const rows = Array.from(resourceTable.querySelectorAll('tbody tr'));
    if (rows.length < 50) return; // Only use virtual scroll for large lists
    
    const items = rows.map(row => ({
        id: row.dataset.id,
        name: row.querySelector('.resource-name')?.textContent || '',
        type: row.querySelector('.resource-type')?.textContent || '',
        status: row.querySelector('.resource-status')?.textContent || '',
        cost: row.querySelector('.resource-cost')?.textContent || '',
        location: row.querySelector('.resource-location')?.textContent || ''
    }));
    
    const virtualScroll = new VirtualScroll({
        container: resourceTable.parentElement,
        itemHeight: 50,
        buffer: 10,
        items: items,
        renderItem: (item, index) => {
            const row = document.createElement('div');
            row.className = 'flex items-center p-3 border-b border-slate-700 hover:bg-slate-800 transition-colors';
            row.innerHTML = `
                <div class="flex-1 resource-name text-sm font-medium text-slate-200">${item.name}</div>
                <div class="w-48 resource-type text-xs text-slate-400">${item.type}</div>
                <div class="w-24 resource-status text-xs">
                    <span class="px-2 py-1 rounded ${item.status === 'Active' ? 'bg-green-900/50 text-green-400' : 'bg-yellow-900/50 text-yellow-400'}">${item.status}</span>
                </div>
                <div class="w-24 resource-cost text-sm font-mono text-slate-300">${item.cost}</div>
                <div class="w-32 resource-location text-xs text-slate-400">${item.location}</div>
            `;
            return row;
        }
    });
    
    return virtualScroll;
}

// Auto-export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { VirtualScroll, debounce, throttle, initVirtualScroll };
}
