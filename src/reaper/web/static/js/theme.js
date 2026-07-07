/**
 * Shared Socket.IO client + Chart.js live metrics (FinOps dashboard, home, monitor).
 * Emissions are throttled server-side (see REAPER_METRICS_EMIT_SEC / Azure Monitor cadence).
 */
(function () {
    // Use dark theme colors by default (theme functionality removed)
    const GRID = 'rgba(255, 255, 255, 0.08)';
    const TICK = '#94a3b8';
    const CHART_PRIMARY = '#06b6d4';
    const CHART_PRIMARY_FILL = 'rgba(6, 182, 212, 0.15)';
    const CHART_SECONDARY = '#8b5cf6';
    const CHART_WARNING = '#f59e0b';
    
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
                const scopeSelect = document.getElementById('projectScopeFilter');
                const scope = scopeSelect ? scopeSelect.value : '';
                let url = '/api/dashboard/finops-charts';
                if (scope) {
                    url += '?resource_group=' + encodeURIComponent(scope);
                }
                const res = await fetch(url);
                const body = await res.json();
                if (!body.charts) {
                    return;
                }
                const c = body.charts;
                
                // Parallel chart updates for better performance
                const updates = [];
                
                if (state.burnChart && c.cost_vs_budget) {
                    updates.push(Promise.resolve().then(() => {
                        state.burnChart.data.labels = c.cost_vs_budget.labels || [];
                        state.burnChart.data.datasets[0].data = c.cost_vs_budget.cumulative_spend || [];
                        state.burnChart.data.datasets[1].data = c.cost_vs_budget.budget_pace || [];
                        state.burnChart.update('none');
                    }));
                }
                if (state.serviceChart && c.services) {
                    updates.push(Promise.resolve().then(() => {
                        state.serviceChart.data.labels = c.services.labels || [];
                        state.serviceChart.data.datasets[0].data = c.services.data || [];
                        state.serviceChart.update('none');
                    }));
                }
                if (state.familyChart && c.families) {
                    updates.push(Promise.resolve().then(() => {
                        state.familyChart.data.labels = c.families.labels || [];
                        state.familyChart.data.datasets[0].data = c.families.cpu || [];
                        state.familyChart.data.datasets[1].data = c.families.memory_gib || [];
                        state.familyChart.update('none');
                    }));
                }
                if (state.heatmapChart && c.hourly_cpu) {
                    updates.push(Promise.resolve().then(() => {
                        const vals = c.hourly_cpu.values || [];
                        state.heatmapChart.data.labels = c.hourly_cpu.labels || [];
                        state.heatmapChart.data.datasets[0].data = vals;
                        state.heatmapChart.data.datasets[0].backgroundColor = heatColors(vals);
                        state.heatmapChart.update('none');
                    }));
                }
                
                // Execute all updates in parallel
                await Promise.all(updates);
            } catch (e) {
                console.warn('[reaper] finops charts refresh failed', e);
            }
        }

        // Expose refresh globally for context switcher
        window.reaperDashboardRefreshCharts = refresh;

        // Delay initial refresh to not block page render
        setTimeout(() => {
            refresh();
            setInterval(refresh, 90000);
        }, 300);
    }

    // Use DOMContentLoaded instead of load for faster initialization
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDashboardCharts);
    } else {
        initDashboardCharts();
    }

    function initDashboardCharts() {
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
            
            // Lazy load finops charts with intersection observer
            if (document.getElementById('burnAreaChart')) {
                initFinopsDashboardChartsLazy(state);
            }
        } catch (error) {
            console.warn("Telemetry Canvas stream initialization deferred safely: ", error);
        }
    }

    function initFinopsDashboardChartsLazy(state) {
        // Use IntersectionObserver for lazy loading charts when they come into viewport
        if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        initFinopsDashboardCharts(state);
                        observer.unobserve(entry.target);
                    }
                });
            }, { rootMargin: '50px' });

            // Observe the dashboard container
            const dashboardContainer = document.querySelector('.app-main');
            if (dashboardContainer) {
                observer.observe(dashboardContainer);
            } else {
                // Fallback: initialize after a short delay
                setTimeout(() => initFinopsDashboardCharts(state), 100);
            }
        } else {
            // Fallback for browsers without IntersectionObserver
            setTimeout(() => initFinopsDashboardCharts(state), 200);
        }
    }
})();

// === Global Console Terminal Functions ===

(function() {
    // Set up console log listener when socket is available
    function setupConsoleListener() {
        const sock = window.__reaperEnsureSocket ? window.__reaperEnsureSocket() : null;
        if (sock && !window.__reaperConsoleHooked) {
            window.__reaperConsoleHooked = true;
            sock.on('new_log', function (msg) {
                const output = document.getElementById('log-output');
                if (!output) return;
                
                const logEntry = document.createElement('p');
                
                // Color-code based on log content
                let colorClass = 'text-cyan-200';
                if (msg.data.includes('❌') || msg.data.includes('error')) {
                    colorClass = 'text-red-400';
                } else if (msg.data.includes('✅') || msg.data.includes('success')) {
                    colorClass = 'text-green-400';
                } else if (msg.data.includes('⚠️') || msg.data.includes('warning')) {
                    colorClass = 'text-yellow-400';
                }
                
                logEntry.className = `log-line ${colorClass}`;
                logEntry.innerText = `[${new Date().toLocaleTimeString()}] ${msg.data}`;
                output.appendChild(logEntry);
                output.scrollTop = output.scrollHeight;
            });
        }
    }
    
    // Try to set up immediately
    setupConsoleListener();
    
    // Also set up when DOM is loaded in case socket isn't ready yet
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupConsoleListener);
    }
})();

window.startLogStream = function() {
    const sock = window.__reaperEnsureSocket ? window.__reaperEnsureSocket() : null;
    const output = document.getElementById('log-output');
    
    if (!sock) {
        if (output) {
            const errorEntry = document.createElement('p');
            errorEntry.className = 'log-line text-red-400';
            errorEntry.innerText = '❌ WebSocket connection not available. Please refresh the page.';
            output.appendChild(errorEntry);
        }
        console.error('WebSocket connection not available for log streaming');
        return;
    }
    
    if (output) {
        const statusEntry = document.createElement('p');
        statusEntry.className = 'log-line system-msg';
        statusEntry.innerText = '> Connecting to log stream...';
        output.appendChild(statusEntry);
    }
    
    sock.emit('start_log_stream');
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
