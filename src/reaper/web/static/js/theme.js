// Function to apply theme
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('reaper-theme', theme);
    
    // Optional: Update any theme-specific icons in the UI
    const themeStatus = document.getElementById('theme-status-text');
    if (themeStatus) themeStatus.innerText = theme.toUpperCase() + " MODE";
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
}

/**
 * Shared Socket.IO client + Chart.js live metrics (FinOps dashboard, home, monitor).
 * Emissions are throttled server-side (see REAPER_METRICS_EMIT_SEC / Azure Monitor cadence).
 */
(function () {
    const GRID = 'rgba(255, 255, 255, 0.06)';
    const TICK = '#6b7280';
    const CHART_PRIMARY = '#5b8def';
    const CHART_PRIMARY_FILL = 'rgba(91, 141, 239, 0.15)';
    const CHART_SECONDARY = '#6b7f9e';
    const CHART_WARNING = '#c9a227';

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
    });
})();
