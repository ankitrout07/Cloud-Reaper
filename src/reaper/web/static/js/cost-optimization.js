/**
 * Cost Optimization page — analysis, reports, and implementation tracking
 */
(function () {
    'use strict';

    let allRecommendations = [];
    let filteredRecommendations = [];
    let isAuthRequired = true; // This page requires authentication

    const PRIORITY_BADGE = {
        critical: 'badge-error',
        high: 'badge-warning',
        medium: 'badge',
        low: 'badge-success',
    };

    function escapeHtml(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function setActiveTab(tabId) {
        ['recommendations', 'reports', 'implementation'].forEach(function (id) {
            const pane = document.getElementById('content-' + id);
            const btn = document.getElementById('tab-' + id);
            if (pane) pane.classList.toggle('hidden', id !== tabId);
            if (btn) btn.classList.toggle('active', id === tabId);
        });
    }

    function showLoading(container, message) {
        container.innerHTML =
            '<div class="loading-block">' +
            '<div class="spinner" role="status" aria-label="Loading"></div>' +
            '<p>' + escapeHtml(message) + '</p></div>';
    }

    window.runAnalysis = async function () {
        const container = document.getElementById('recommendations-container');
        if (!container) return;

        showLoading(container, 'Running comprehensive cost analysis…');

        try {
            const response = await fetch('/api/cost-optimization/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: 'azure' }),
            });
            const data = await response.json();

            if (data.status === 'success') {
                allRecommendations = data.recommendations || [];
                filteredRecommendations = allRecommendations.slice();
                updateSummary(data.summary);
                renderRecommendations(filteredRecommendations);
                loadReportsData();
            } else {
                container.innerHTML =
                    '<div class="empty-state-pro"><p class="empty-state-pro__title text-error">Analysis failed</p>' +
                    '<p class="empty-state-pro__desc">' + escapeHtml(data.message) + '</p></div>';
            }
        } catch (error) {
            container.innerHTML =
                '<div class="empty-state-pro"><p class="empty-state-pro__title text-error">Error</p>' +
                '<p class="empty-state-pro__desc">' + escapeHtml(error.message) + '</p></div>';
        }
    };

    async function loadReportsData() {
        try {
            const endpoints = [
                { url: '/api/cost-reports/executive-summary?provider=azure&period=monthly', fn: displayExecutiveSummary, key: 'summary' },
                { url: '/api/cost-reports/trends', fn: displayTrends, key: 'trends_data' },
                { url: '/api/cost-reports/category-analysis', fn: displayCategoryAnalysis, key: 'category_analysis' },
                { url: '/api/cost-reports/risk-assessment', fn: displayRiskAssessment, key: 'risk_assessment' },
                { url: '/api/cost-reports/next-steps', fn: displayNextSteps, key: 'next_steps' },
                { url: '/api/cost-reports/implementation-progress', fn: displayImplementationProgress, key: 'progress' },
            ];

            for (const ep of endpoints) {
                const res = await fetch(ep.url);
                const data = await res.json();
                if (data.status === 'success' && data[ep.key] != null) {
                    ep.fn(data[ep.key]);
                }
            }
        } catch (error) {
            console.warn('[cost-optimization] reports load failed', error);
        }
    }

    function dataCell(label, value, valueClass) {
        return (
            '<div class="data-cell">' +
            '<div class="data-cell__label">' + escapeHtml(label) + '</div>' +
            '<div class="data-cell__value' + (valueClass ? ' ' + valueClass : '') + '">' + value + '</div></div>'
        );
    }

    function displayExecutiveSummary(summary) {
        const container = document.getElementById('executive-summary-content');
        if (!container) return;

        const opportunities = (summary.top_opportunities || [])
            .map(function (rec) {
                return (
                    '<li class="rec-card__panel">' +
                    '<div class="rec-card__title text-accent">' + escapeHtml(rec.title) + '</div>' +
                    '<div class="stat-card__hint">Savings: $' + rec.estimated_monthly_savings.toFixed(2) + '/mo</div></li>'
                );
            })
            .join('');

        container.innerHTML =
            '<div class="data-grid data-grid--4">' +
            dataCell('Total Potential Savings', '$' + summary.total_potential_savings.toFixed(2), 'stat-card__value--success') +
            dataCell('Implemented Savings', '$' + summary.total_implemented_savings.toFixed(2), 'stat-card__value--accent') +
            dataCell('Realization Rate', summary.savings_realization_rate.toFixed(1) + '%') +
            dataCell('Recommendations', String(summary.total_recommendations)) +
            '</div>' +
            (opportunities
                ? '<h3 class="section-card__title mt-4 mb-2">Top Opportunities</h3><ul class="space-y-2">' + opportunities + '</ul>'
                : '');
    }

    function displayTrends(trendsData) {
        const container = document.getElementById('trends-content');
        if (!container) return;

        if (!trendsData.trends || trendsData.trends.length === 0) {
            container.innerHTML = '<p class="text-muted">No trend data available yet.</p>';
            return;
        }

        let html = '<div class="space-y-3">';
        trendsData.trends.forEach(function (trend) {
            html +=
                '<div class="rec-card__panel">' +
                '<div class="flex justify-between items-center mb-2 flex-wrap gap-2">' +
                '<span class="font-semibold">' + escapeHtml(trend.period) + '</span>' +
                '<span class="text-accent">$' + trend.savings.toFixed(2) + ' (' + trend.savings_percentage.toFixed(1) + '%)</span></div>' +
                '<div class="data-grid data-grid--4 text-sm">' +
                dataCell('Total Cost', '$' + trend.total_cost.toFixed(2)) +
                dataCell('Optimized', '$' + trend.optimized_cost.toFixed(2)) +
                dataCell('Resources', String(trend.resource_count)) +
                dataCell('Implemented', trend.implemented_recommendations + '/' + trend.recommendations_count) +
                '</div></div>';
        });
        html += '</div>';

        if (trendsData.analysis && trendsData.analysis.trend_direction) {
            const dir = trendsData.analysis.trend_direction;
            const cls = dir === 'decreasing' ? 'text-success' : 'text-error';
            html += '<p class="mt-4 text-center text-secondary">Trend: <span class="' + cls + ' font-semibold">' + escapeHtml(dir) + '</span></p>';
        }

        container.innerHTML = html;
    }

    function displayCategoryAnalysis(categoryAnalysis) {
        const container = document.getElementById('category-analysis-content');
        if (!container) return;

        let html = '<div class="space-y-3">';
        for (const [category, data] of Object.entries(categoryAnalysis)) {
            html +=
                '<div class="rec-card__panel">' +
                '<div class="flex justify-between items-center mb-2">' +
                '<span class="font-semibold capitalize">' + escapeHtml(category) + '</span>' +
                '<span class="text-success">$' + data.total_savings.toFixed(2) + '</span></div>' +
                '<div class="data-grid">' +
                dataCell('Recommendations', String(data.recommendation_count)) +
                dataCell('Avg Savings', '$' + data.average_savings_per_recommendation.toFixed(2)) +
                '</div></div>';
        }
        html += '</div>';
        container.innerHTML = html;
    }

    function displayRiskAssessment(riskAssessment) {
        const container = document.getElementById('risk-assessment-content');
        if (!container) return;

        const quickWins = (riskAssessment.quick_wins || [])
            .map(function (rec) {
                return (
                    '<li class="bg-success-subtle p-3 rounded-lg border border-success">' +
                    '<div class="font-semibold text-success">' + escapeHtml(rec.title) + '</div>' +
                    '<div class="text-sm text-secondary">$' + rec.estimated_monthly_savings.toFixed(2) + '/mo · Risk: ' + escapeHtml(rec.risk_level) + '</div></li>'
                );
            })
            .join('');

        const order = (riskAssessment.recommended_implementation_order || [])
            .slice(0, 5)
            .map(function (rec, i) {
                const border =
                    rec.risk_level === 'safe'
                        ? 'priority-low'
                        : rec.risk_level === 'low'
                          ? 'priority-medium'
                          : rec.risk_level === 'medium'
                            ? 'priority-high'
                            : 'priority-critical';
                return (
                    '<div class="rec-card ' + border + ' p-3">' +
                    '<div class="font-semibold">' + (i + 1) + '. ' + escapeHtml(rec.title) + '</div>' +
                    '<div class="text-sm text-secondary">$' + rec.estimated_monthly_savings.toFixed(2) + '/mo · Risk: ' + escapeHtml(rec.risk_level) + '</div></div>'
                );
            })
            .join('');

        container.innerHTML =
            '<div class="space-y-4">' +
            '<div><h3 class="section-card__title mb-3">Quick Wins</h3><ul class="space-y-2">' + quickWins + '</ul></div>' +
            '<div><h3 class="section-card__title mb-3">Implementation Order</h3><div class="space-y-2">' + order + '</div></div></div>';
    }

    function displayNextSteps(nextSteps) {
        const container = document.getElementById('next-steps-content');
        if (!container) return;

        container.innerHTML = nextSteps
            .map(function (step) {
                return (
                    '<div class="rec-card__panel flex items-start gap-3">' +
                    '<span class="text-accent" aria-hidden="true">→</span>' +
                    '<span>' + escapeHtml(step) + '</span></div>'
                );
            })
            .join('');
    }

    function displayImplementationProgress(progress) {
        const container = document.getElementById('implementation-progress-content');
        if (!container) return;

        if (progress.message) {
            container.innerHTML = '<p class="text-muted">' + escapeHtml(progress.message) + '</p>';
            return;
        }

        const completion = progress.completion_percentage;
        const bd = progress.status_breakdown;

        container.innerHTML =
            '<div class="space-y-4">' +
            '<div class="rec-card__panel">' +
            '<div class="flex justify-between items-center mb-3">' +
            '<span class="font-semibold">Overall Progress</span>' +
            '<span class="text-accent">' + completion.toFixed(1) + '% complete</span></div>' +
            '<div class="progress-bar h-2"><div class="progress-fill" style="width:' + completion + '%"></div></div>' +
            '<div class="flex justify-between text-sm mt-2 text-muted">' +
            '<span>Completed: ' + bd.completed + '</span><span>In progress: ' + bd.in_progress + '</span></div></div>' +
            '<div class="rec-card__panel">' +
            '<h3 class="section-card__title mb-3">Status Breakdown</h3>' +
            '<div class="space-y-2 text-sm">' +
            '<div class="flex justify-between"><span>Planned</span><span class="text-muted">' + bd.planned + '</span></div>' +
            '<div class="flex justify-between"><span>In progress</span><span class="text-info">' + bd.in_progress + '</span></div>' +
            '<div class="flex justify-between"><span>Completed</span><span class="text-success">' + bd.completed + '</span></div>' +
            '<div class="flex justify-between"><span>Failed</span><span class="text-error">' + bd.failed + '</span></div>' +
            '</div></div></div>';
    }

    window.showRecommendations = function () {
        setActiveTab('recommendations');
    };

    window.showReports = function () {
        setActiveTab('reports');
        const trends = document.getElementById('trends-content');
        if (trends && trends.dataset.loaded !== 'true') {
            loadReportsData().then(function () {
                trends.dataset.loaded = 'true';
            });
        }
    };

    window.showImplementation = function () {
        setActiveTab('implementation');
        const progress = document.getElementById('implementation-progress-content');
        if (progress && progress.dataset.loaded !== 'true') {
            loadReportsData().then(function () {
                progress.dataset.loaded = 'true';
            });
        }
    };

    window.generateReport = async function () {
        const period = document.getElementById('report-period').value;
        const format = document.getElementById('report-format').value;

        try {
            const response = await fetch('/api/cost-reports/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: 'azure', period: period, format: format }),
            });
            const data = await response.json();

            if (data.status === 'success') {
                if (format === 'json') {
                    const blob = new Blob([data.report], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'cost-optimization-report-' + period + '.' + format;
                    a.click();
                    URL.revokeObjectURL(url);
                } else if (typeof showToast === 'function') {
                    showToast('Report generated (' + format + ')', 'success');
                } else {
                    alert('Report generated successfully in ' + format + ' format');
                }
            } else {
                alert('Error generating report: ' + data.message);
            }
        } catch (error) {
            alert('Error generating report: ' + error.message);
        }
    };

    function updateSummary(summary) {
        const set = function (id, text) {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        };
        set('total-recs', summary.total_recommendations);
        set('monthly-savings', '$' + summary.total_monthly_savings.toFixed(2));
        set('high-priority', summary.by_priority?.high || 0);
        if (summary.total_recommendations > 0) {
            const pct = (summary.total_monthly_savings / summary.total_recommendations).toFixed(0);
            set('savings-percent', pct + '%');
        }
    }

    function renderRecommendations(recommendations) {
        const container = document.getElementById('recommendations-container');
        if (!container) return;

        if (recommendations.length === 0) {
            container.innerHTML =
                '<div class="empty-state-pro">' +
                '<p class="empty-state-pro__title">No matches</p>' +
                '<p class="empty-state-pro__desc">Try adjusting your filters or run a new analysis.</p></div>';
            return;
        }

        container.innerHTML = recommendations.map(renderRecommendationCard).join('');
    }

    function jsString(s) {
        return String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    }

    function renderRecommendationCard(rec) {
        const badgeClass = PRIORITY_BADGE[rec.priority] || 'badge';
        const steps = (rec.implementation_steps || [])
            .map(function (s) {
                return '<li>' + escapeHtml(s) + '</li>';
            })
            .join('');
        const issues = (rec.potential_issues || [])
            .map(function (i) {
                return '<li>' + escapeHtml(i) + '</li>';
            })
            .join('');

        return (
            '<article class="rec-card priority-' + escapeHtml(rec.priority) + '">' +
            '<div class="rec-card__body">' +
            '<div class="flex-1 min-w-0">' +
            '<div class="rec-card__meta">' +
            '<span class="badge ' + badgeClass + '">' + escapeHtml(rec.priority) + '</span>' +
            '<span class="badge">' + escapeHtml(rec.category) + '</span></div>' +
            '<h3 class="rec-card__title">' + escapeHtml(rec.title) + '</h3>' +
            '<p class="rec-card__desc">' + escapeHtml(rec.description) + '</p></div>' +
            '<div class="rec-card__savings">' +
            '<div class="rec-card__savings-amount">$' + rec.estimated_monthly_savings.toFixed(2) + '</div>' +
            '<div class="stat-card__hint">/month</div>' +
            '<div class="stat-card__value stat-card__value--accent text-lg">' + (rec.estimated_savings_percentage * 100).toFixed(0) + '%</div>' +
            '<div class="stat-card__hint">reduction</div></div></div>' +
            '<div class="rec-card__panel">' +
            '<div class="data-grid">' +
            dataCell('Resource', escapeHtml(rec.resource_name)) +
            dataCell('Type', escapeHtml(rec.resource_type)) +
            dataCell('Current Cost', '$' + rec.current_cost.toFixed(2) + '/mo') +
            dataCell('Risk', escapeHtml(rec.risk_level)) +
            '</div></div>' +
            '<div class="rec-card__panel">' +
            '<p class="section-card__title text-sm mb-2">Recommended Action</p>' +
            '<p class="text-accent mb-3">' + escapeHtml(rec.recommended_action) + '</p>' +
            (steps ? '<p class="section-card__title text-sm mb-2">Implementation Steps</p><ol class="list-decimal list-inside text-sm text-secondary space-y-1">' + steps + '</ol>' : '') +
            (issues ? '<p class="text-warning text-sm font-bold mt-4 mb-2">Potential Issues</p><ul class="list-disc list-inside text-sm text-secondary space-y-1">' + issues + '</ul>' : '') +
            '</div>' +
            '<div class="rec-card__actions">' +
            '<button type="button" class="btn btn-ghost btn-sm" onclick="viewDetails(\'' + jsString(rec.id) + '\')">Details</button>' +
            '<button type="button" class="btn btn-ghost btn-sm" onclick="trackImplementation(\'' + jsString(rec.id) + '\')">Track</button>' +
            '<button type="button" class="btn btn-primary btn-sm" onclick="implementRecommendation(\'' + jsString(rec.id) + '\')">Implement</button>' +
            '</div></article>'
        );
    }

    window.filterRecommendations = function () {
        const priorityFilter = document.getElementById('priority-filter').value;
        const categoryFilter = document.getElementById('category-filter').value;
        const riskFilter = document.getElementById('risk-filter').value;

        filteredRecommendations = allRecommendations.filter(function (rec) {
            if (priorityFilter !== 'all' && rec.priority !== priorityFilter) return false;
            if (categoryFilter !== 'all' && rec.category !== categoryFilter) return false;
            if (riskFilter !== 'all' && rec.risk_level !== riskFilter) return false;
            return true;
        });

        renderRecommendations(filteredRecommendations);
    };

    window.viewDetails = function (recId) {
        const rec = allRecommendations.find(function (r) {
            return r.id === recId;
        });
        if (rec) alert('Full details for ' + rec.title + ':\n\n' + JSON.stringify(rec, null, 2));
    };

    window.trackImplementation = async function (recId) {
        const status = prompt('Current implementation status?', 'planned');
        const notes = prompt('Notes (optional)') || '';
        if (!status) return;

        try {
            const response = await fetch('/api/cost-reports/track-status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ recommendation_id: recId, status: status, notes: notes }),
            });
            const data = await response.json();
            if (data.status === 'success') {
                if (typeof showToast === 'function') showToast('Status tracked', 'success');
                else alert('Status tracked successfully!');
            } else {
                alert('Error: ' + data.message);
            }
        } catch (error) {
            alert('Error tracking status: ' + error.message);
        }
    };

    window.implementRecommendation = function (recId) {
        const rec = allRecommendations.find(function (r) {
            return r.id === recId;
        });
        if (rec && confirm('Implement: ' + rec.title + '?\n\nThis may modify cloud infrastructure.')) {
            alert('Implementation triggered for: ' + rec.title + '\n\n(Demo mode — production would execute via cloud APIs.)');
        }
    };

    window.exportReport = function () {
        if (allRecommendations.length === 0) {
            alert('No recommendations to export. Run analysis first.');
            return;
        }

        const summary = {
            generated_at: new Date().toISOString(),
            total_recommendations: allRecommendations.length,
            total_monthly_savings: allRecommendations.reduce(function (sum, rec) {
                return sum + rec.estimated_monthly_savings;
            }, 0),
            recommendations: allRecommendations,
        };

        const blob = new Blob([JSON.stringify(summary, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'cost-optimization-report.json';
        a.click();
        URL.revokeObjectURL(url);
    };

    function loadInitialData() {
        fetch('/api/cost-optimization/summary')
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                if (data.status === 'success' && data.summary.total_recommendations > 0) {
                    updateSummary(data.summary);
                    return fetch('/api/cost-optimization/categories');
                }
            })
            .then(function (r) {
                if (!r) return;
                return r.json();
            })
            .then(function (data) {
                if (data && data.status === 'success') {
                    Object.values(data.categories).forEach(function (catData) {
                        catData.recommendations.forEach(function (rec) {
                            if (!allRecommendations.find(function (r) {
                                return r.id === rec.id;
                            })) {
                                allRecommendations.push(rec);
                            }
                        });
                    });
                    filteredRecommendations = allRecommendations.slice();
                    renderRecommendations(filteredRecommendations);
                }
            })
            .catch(function () {
                /* no prior analysis */
            });
    }

    // ── Cloud Provider Authentication Event Handlers ───────────────────────────────
    function handleProviderActivated(event) {
        const { authenticated, subscription_id } = event.detail;

        if (authenticated) {
            console.log('[cost-optimization] Provider activated, loading data...');
            // Enable page features
            const authElements = document.querySelectorAll('.auth-required');
            authElements.forEach(el => {
                el.disabled = false;
                el.classList.remove('opacity-40', 'pointer-events-none');
            });

            // Un-hide content
            const hiddenElements = document.querySelectorAll('[data-auth-hidden="true"]');
            hiddenElements.forEach(el => el.classList.remove('hidden'));

            // Load data automatically
            loadInitialData();
        }
    }

    function handleProviderDeactivated(event) {
        const { authenticated } = event.detail;

        if (!authenticated && isAuthRequired) {
            console.log('[cost-optimization] Provider deactivated, disabling features...');
            // Disable page features
            const authElements = document.querySelectorAll('.auth-required');
            authElements.forEach(el => {
                el.disabled = true;
                el.classList.add('opacity-40', 'pointer-events-none');
            });

            // Hide content
            const hiddenElements = document.querySelectorAll('[data-auth-hidden="true"]');
            hiddenElements.forEach(el => el.classList.add('hidden'));

            // Show auth prompt
            if (typeof window.setAuthOverlay === 'function') {
                window.setAuthOverlay(true);
            }
        }
    }

    // ── Initialization ───────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        // Listen for cloud provider activation events
        window.addEventListener('cloudProviderActivated', function (event) {
            if (event.detail.authenticated) {
                handleProviderActivated(event);
            } else {
                handleProviderDeactivated(event);
            }
        });

        // Check initial authentication state
        if (typeof window.getAuthState === 'function') {
            const initialState = window.getAuthState();
            if (initialState.authenticated) {
                handleProviderActivated({ detail: initialState });
            } else if (isAuthRequired) {
                handleProviderDeactivated({ detail: initialState });
            }
        }

        // Load initial data if authenticated
        loadInitialData();
    });

    document.body.addEventListener('htmx:afterSwap', function () {
        // Re-attach event listeners after SPA navigation
        if (document.getElementById('recommendations-container')) {
            // Check authentication state again after navigation
            if (typeof window.getAuthState === 'function') {
                const currentState = window.getAuthState();
                if (currentState.authenticated) {
                    handleProviderActivated({ detail: currentState });
                } else if (isAuthRequired) {
                    handleProviderDeactivated({ detail: currentState });
                }
            }
            loadInitialData();
        }
    });
})();
