// Enhanced theme management with better persistence and UI updates
function applyTheme(theme) {
    // Validate theme value
    if (!theme || !['dark', 'light'].includes(theme)) {
        theme = 'dark';
    }
    
    // Apply to document
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('reaper-theme', theme);
    
    // Update theme-specific UI elements
    const themeStatus = document.getElementById('theme-status-text');
    if (themeStatus) themeStatus.innerText = theme.toUpperCase() + ' MODE';
    
    const themeToggleBtn = document.querySelector('.theme-toggle-btn');
    if (themeToggleBtn) {
        if (theme === 'dark') {
            themeToggleBtn.innerHTML = '<i class="fas fa-sun"></i>';
            themeToggleBtn.title = 'Switch to Light Mode';
        } else {
            themeToggleBtn.innerHTML = '<i class="fas fa-moon"></i>';
            themeToggleBtn.title = 'Switch to Dark Mode';
        }
    }
    
    // Update chart colors if Chart.js is loaded
    if (typeof Chart !== 'undefined') {
        updateChartColors(theme);
    }
}

// Update Chart.js colors based on theme
function updateChartColors(theme) {
    const colors = theme === 'dark' ? {
        grid: 'rgba(255, 255, 255, 0.08)',
        tick: '#94a3b8',
        primary: '#06b6d4',
        secondary: '#8b5cf6',
        success: '#10b981',
        warning: '#f59e0b',
        error: '#ef4444'
    } : {
        grid: 'rgba(15, 23, 42, 0.08)',
        tick: '#64748b',
        primary: '#0891b2',
        secondary: '#7c3aed',
        success: '#059669',
        warning: '#d97706',
        error: '#dc2626'
    };
    
    // Store globally for use by other scripts
    window.__chartColors = colors;
}

// Initial check on page load
(function() {
    const savedTheme = localStorage.getItem('reaper-theme') || 'dark';
    applyTheme(savedTheme);
})();

// Toggle function for the button in Settings
function toggleAppTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
    
    // Show toast notification
    if (typeof showToast === 'function') {
        showToast(`Switched to ${newTheme} mode`, 'success');
    }
}

// Auto-detect system preference on first visit
(function detectSystemTheme() {
    if (!localStorage.getItem('reaper-theme')) {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        applyTheme(prefersDark ? 'dark' : 'light');
    }
})();

// Listen for system theme changes
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!localStorage.getItem('reaper-theme')) {
        applyTheme(e.matches ? 'dark' : 'light');
    }
});

/**
 * Shared Socket.IO client + Chart.js live metrics (FinOps dashboard, home, monitor).
 * Emissions are throttled server-side (see REAPER_METRICS_EMIT_SEC / Azure Monitor cadence).
 */
(function () {
    // Use theme-aware colors or fallback to dark theme colors
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const GRID = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(15, 23, 42, 0.08)';
    const TICK = isDark ? '#94a3b8' : '#64748b';
    const CHART_PRIMARY = isDark ? '#06b6d4' : '#0891b2';
    const CHART_PRIMARY_FILL = isDark ? 'rgba(6, 182, 212, 0.15)' : 'rgba(8, 145, 178, 0.15)';
    const CHART_SECONDARY = isDark ? '#8b5cf6' : '#7c3aed';
    const CHART_WARNING = isDark ? '#f59e0b' : '#d97706';
    
    window.__reaperEnsureSocket = function () {
        if (typeof io === 'undefined') {
            return null;
        }
        if (!window.__reaperSocket) {
            window.__reaperSocket = io();
        }
        return window.__reaperSocket;
    };

    function trimLine(chart, maxPts) {
        while (chart.data.labels.length > maxPts) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
        }
    }

    function createCpuLineChart(canvasId, options) {
        const el = document.getElementById(canvasId);
        if (!el || typeof Chart === 'undefined') {
            return null;
        }
        const maxPts = options.maxPoints || 20;
        const border = options.borderColor || CHART_PRIMARY;
        const fill = options.backgroundColor || CHART_PRIMARY_FILL;
        const showX = options.showXLabels !== false;
        return new Chart(el.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: options.label || 'Avg CPU Utilization (%)',
                        borderColor: border,
                        backgroundColor: fill,
                        data: [],
                        fill: true,
                        tension: 0.4,
                        borderWidth: 2,
                        pointRadius: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: { legend: { display: !!options.showLegend } },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        grid: { color: GRID },
                        ticks: { color: TICK, font: { size: 9 } },
                    },
                    x: {
                        display: showX,
                        grid: { display: false },
                        ticks: { color: TICK, font: { size: 9 }, maxRotation: 0 },
                    },
                },
            },
        });
    }

    function hookMetricSocket(state) {
        const sock = window.__reaperEnsureSocket();
        if (!sock || window.__reaperMetricHooked) {
            return;
        }
        window.__reaperMetricHooked = true;
        sock.on('metric_update', function (payload) {
            const v = payload.value;
            const t = payload.time;
            if (state.computeChart) {
                trimLine(state.computeChart, 20);
                state.computeChart.data.labels.push(t);
                state.computeChart.data.datasets[0].data.push(v);
                state.computeChart.update('none');
            }
            if (state.bigMonitorChart) {
                trimLine(state.bigMonitorChart, 20);
                state.bigMonitorChart.data.labels.push(t);
                state.bigMonitorChart.data.datasets[0].data.push(v);
                state.bigMonitorChart.update('none');
            }
            const cpuEl = document.getElementById('live-cpu');
            if (cpuEl) {
                cpuEl.innerText = v + '%';
            }
            const netEl = document.getElementById('live-net');
            if (netEl) {
                netEl.innerText = (v / 4).toFixed(1);
            }
            const thrEl = document.getElementById('live-threads');
            if (thrEl) {
                thrEl.innerText = String(Math.floor(v * 2.5));
            }
        });
    }

    function heatColors(values) {
        const mx = Math.max.apply(null, values.concat([1]));
        return values.map(function (x) {
            const a = Math.min(1, x / mx);
            const r = Math.round(40 + a * 50);
            const g = Math.round(70 + a * 70);
            const b = Math.round(120 + a * 115);
            return 'rgba(' + r + ',' + g + ',' + b + ',0.75)';
        });
    }

    function initFinopsDashboardCharts(state) {
        const burnEl = document.getElementById('burnAreaChart');
        if (!burnEl) {
            return;
        }

        state.burnChart = new Chart(burnEl.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Cumulative spend',
                        data: [],
                        borderColor: CHART_PRIMARY,
                        backgroundColor: CHART_PRIMARY_FILL,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                    },
                    {
                        label: 'Budget pace',
                        data: [],
                        borderColor: CHART_WARNING,
                        backgroundColor: 'transparent',
                        fill: false,
                        tension: 0,
                        borderDash: [6, 4],
                        pointRadius: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: { legend: { labels: { color: TICK } } },
                scales: {
                    y: { beginAtZero: true, grid: { color: GRID }, ticks: { color: TICK } },
                    x: { grid: { display: false }, ticks: { color: TICK, maxRotation: 45 } },
                },
            },
        });

        state.serviceChart = new Chart(document.getElementById('serviceBarChart').getContext('2d'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Spend (30d)',
                        data: [],
                        backgroundColor: [CHART_PRIMARY, '#4a6fa8', CHART_SECONDARY, '#3d4550'],
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: GRID }, ticks: { color: TICK } },
                    x: { grid: { display: false }, ticks: { color: TICK } },
                },
            },
        });

        state.familyChart = new Chart(document.getElementById('familyStackChart').getContext('2d'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'CPU %',
                        data: [],
                        backgroundColor: 'rgba(91, 141, 239, 0.65)',
                        yAxisID: 'y',
                    },
                    {
                        label: 'Memory GiB (avail.)',
                        data: [],
                        backgroundColor: 'rgba(107, 127, 158, 0.55)',
                        yAxisID: 'y1',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: { legend: { labels: { color: TICK } } },
                scales: {
                    x: { grid: { display: false }, ticks: { color: TICK } },
                    y: {
                        position: 'left',
                        beginAtZero: true,
                        max: 100,
                        title: { display: true, text: 'CPU %', color: TICK },
                        grid: { color: GRID },
                        ticks: { color: TICK },
                    },
                    y1: {
                        position: 'right',
                        beginAtZero: true,
                        title: { display: true, text: 'GiB', color: TICK },
                        grid: { drawOnChartArea: false },
                        ticks: { color: TICK },
                    },
                },
            },
        });

        state.heatmapChart = new Chart(document.getElementById('usageHeatmapChart').getContext('2d'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'CPU %',
                        data: [],
                        backgroundColor: [],
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, max: 100, grid: { color: GRID }, ticks: { color: TICK } },
                    x: { grid: { display: false }, ticks: { color: TICK, maxRotation: 90, minRotation: 45 } },
                },
            },
        });

        async function refresh() {
            try {
                const res = await fetch('/api/dashboard/finops-charts');
                const body = await res.json();
                if (!body.charts) {
                    return;
                }
                const c = body.charts;
                if (state.burnChart && c.cost_vs_budget) {
                    state.burnChart.data.labels = c.cost_vs_budget.labels || [];
                    state.burnChart.data.datasets[0].data = c.cost_vs_budget.cumulative_spend || [];
                    state.burnChart.data.datasets[1].data = c.cost_vs_budget.budget_pace || [];
                    state.burnChart.update('none');
                }
                if (state.serviceChart && c.services) {
                    state.serviceChart.data.labels = c.services.labels || [];
                    state.serviceChart.data.datasets[0].data = c.services.data || [];
                    state.serviceChart.update('none');
                }
                if (state.familyChart && c.families) {
                    state.familyChart.data.labels = c.families.labels || [];
                    state.familyChart.data.datasets[0].data = c.families.cpu || [];
                    state.familyChart.data.datasets[1].data = c.families.memory_gib || [];
                    state.familyChart.update('none');
                }
                if (state.heatmapChart && c.hourly_cpu) {
                    const vals = c.hourly_cpu.values || [];
                    state.heatmapChart.data.labels = c.hourly_cpu.labels || [];
                    state.heatmapChart.data.datasets[0].data = vals;
                    state.heatmapChart.data.datasets[0].backgroundColor = heatColors(vals);
                    state.heatmapChart.update('none');
                }
            } catch (e) {
                console.warn('[reaper] finops charts refresh failed', e);
            }
        }

        refresh();
        setInterval(refresh, 90000);
    }

    window.addEventListener('load', function () {
        if (typeof Chart === 'undefined') {
            return;
        }

        const state = {
            computeChart: null,
            bigMonitorChart: null,
            burnChart: null,
            serviceChart: null,
            familyChart: null,
            heatmapChart: null,
        };

        try {
            if (document.getElementById('computeChart')) {
                const dash = !!document.getElementById('burnAreaChart');
                state.computeChart = createCpuLineChart('computeChart', {
                    borderColor: CHART_PRIMARY,
                    backgroundColor: CHART_PRIMARY_FILL,
                    maxPoints: dash ? 20 : 30,
                    showXLabels: dash,
                    label: 'Avg CPU Utilization (%)',
                });
            }

            if (document.getElementById('bigMonitorChart')) {
                state.bigMonitorChart = createCpuLineChart('bigMonitorChart', {
                    maxPoints: 20,
                    showXLabels: true,
                    showLegend: false,
                });
            }

            hookMetricSocket(state);
            initFinopsDashboardCharts(state);
        } catch (error) {
            console.warn("Telemetry Canvas stream initialization deferred safely: ", error);
        }
    });
})();

// === Global Console Terminal Functions ===

(function() {
    const sock = window.__reaperEnsureSocket ? window.__reaperEnsureSocket() : null;
    if (sock && !window.__reaperConsoleHooked) {
        window.__reaperConsoleHooked = true;
        sock.on('new_log', function (msg) {
            const output = document.getElementById('log-output');
            if (!output) return;
            const logEntry = document.createElement('p');
            logEntry.className = 'log-line text-cyan-200';
            logEntry.innerText = `[${new Date().toLocaleTimeString()}] ${msg.data}`;
            output.appendChild(logEntry);
            output.scrollTop = output.scrollHeight;
        });
    }
})();

window.startLogStream = function() {
    const sock = window.__reaperEnsureSocket ? window.__reaperEnsureSocket() : null;
    if (sock) {
        sock.emit('start_log_stream');
    }
};

window.toggleConsole = function(forceOpen = false) {
    const terminal = document.getElementById('console-terminal');
    if (!terminal) return;
    
    if (forceOpen) {
        terminal.style.display = 'block';
    } else {
        terminal.style.display = (terminal.style.display === 'none') ? 'block' : 'none';
    }

    if (terminal.style.display === 'block') {
        const output = document.getElementById('log-output');
        if (output) output.innerHTML = ''; // Clear previous logs
        window.startLogStream();
    }
};

window.logToConsole = function(msg, type = 'info') {
    const output = document.getElementById('log-output');
    if (!output) return;
    const logEntry = document.createElement('p');
    logEntry.className = type === 'success' ? 'log-line text-green-400' : 'log-line text-slate-400';
    logEntry.innerText = `[${new Date().toLocaleTimeString()}] > ${msg}`;
    output.appendChild(logEntry);
    output.scrollTop = output.scrollHeight;
};
