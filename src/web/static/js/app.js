// Global state
let portfolioData = null;
let priceChart = null;
let pnlChart = null;
let holdingCharts = {};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    updateDateTime();
    fetchPortfolioData();
    
    // Auto-refresh every 30 seconds
    setInterval(fetchPortfolioData, 30000);
    setInterval(updateDateTime, 1000);
});

// Update date/time display
function updateDateTime() {
    const now = new Date();
    const options = { 
        month: 'short', 
        day: 'numeric', 
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    document.getElementById('dateDisplay').textContent = now.toLocaleDateString('en-US', options);
}

// Fetch portfolio data
async function fetchPortfolioData() {
    console.log('Fetching portfolio data...');
    try {
        const response = await fetch('/api/portfolio');
        console.log('Response status:', response.status);
        const result = await response.json();
        console.log('API Result:', result);
        
        if (result.success && result.data) {
            portfolioData = result.data;
            console.log('Portfolio data loaded:', portfolioData);
            updateDashboard();
        } else {
            console.error('API returned error:', result.message);
            showError(result.message || 'Failed to fetch data');
        }
    } catch (error) {
        console.error('Error fetching portfolio:', error);
        showError('Unable to connect to server');
    }
}

// Update all dashboard components
function updateDashboard() {
    if (!portfolioData) return;
    
    updateMetrics();
    updateCharts();
    renderHoldingsCharts();
}

// Update metric cards
function updateMetrics() {
    const { summary } = portfolioData;
    
    // Total Value
    document.getElementById('totalValue').textContent = `₹${formatNumber(summary.total_value)}`;
    
    // Total P&L
    const totalPnlEl = document.getElementById('totalPnl');
    totalPnlEl.textContent = `₹${formatNumber(summary.total_pnl)}`;
    totalPnlEl.style.color = summary.total_pnl >= 0 ? '#bfff00' : '#ff1744';
    
    const pnlBadge = document.getElementById('pnlBadge');
    pnlBadge.textContent = `${summary.total_pnl_percent.toFixed(2)}%`;
    pnlBadge.className = summary.total_pnl >= 0 ? 'metric-badge gain' : 'metric-badge loss';
    
    // P&L Change indicator
    const totalChange = document.getElementById('totalChange');
    totalChange.className = summary.total_pnl >= 0 ? 'metric-change positive' : 'metric-change negative';
    totalChange.querySelector('span').textContent = `${summary.total_pnl_percent.toFixed(2)}%`;
    
    // Gainers & Losers
    const gainersCountEl = document.getElementById('gainersCount');
    gainersCountEl.textContent = summary.gainers;
    gainersCountEl.style.color = '#bfff00';
    
    const losersCountEl = document.getElementById('losersCount');
    losersCountEl.textContent = summary.losers;
    losersCountEl.style.color = '#ff1744';
    
    document.getElementById('gainersText').textContent = `of ${summary.holdings_count} stocks`;
    document.getElementById('losersText').textContent = `of ${summary.holdings_count} stocks`;
}

// Update charts
function updateCharts() {
    const holdings = portfolioData.holdings;
    
    // Prepare data
    const sortedByValue = [...holdings].sort((a, b) => b.value - a.value).slice(0, 10);
    const sortedByPnl = [...holdings].sort((a, b) => b.pnl - a.pnl);
    
    // Price Comparison Chart
    updatePriceChart(sortedByValue);
    
    // P&L Chart
    updatePnLChart(sortedByPnl);
}

// Update price comparison chart
function updatePriceChart(holdings) {
    const ctx = document.getElementById('priceChart').getContext('2d');
    
    // Get top 10 holdings by value
    const topHoldings = holdings.slice(0, 10);
    const labels = topHoldings.map(h => h.symbol);
    
    // Prepare data
    const boughtPrices = topHoldings.map(h => h.avg_price);
    const currentPrices = topHoldings.map(h => h.ltp);
    
    // Calculate point colors based on profit/loss
    const pointColors = currentPrices.map((price, i) => {
        return price >= boughtPrices[i] ? '#bfff00' : '#ff1744';
    });
    
    // Calculate average color for the line
    const profitCount = pointColors.filter(c => c === '#bfff00').length;
    const avgLineColor = profitCount > pointColors.length / 2 ? '#bfff00' : '#ff1744';
    
    // Update existing chart instead of recreating
    if (priceChart) {
        priceChart.data.labels = labels;
        priceChart.data.datasets[0].data = boughtPrices;
        priceChart.data.datasets[1].data = currentPrices;
        priceChart.data.datasets[1].pointBackgroundColor = pointColors;
        priceChart.data.datasets[1].borderColor = avgLineColor;
        priceChart.update('none'); // 'none' animation mode for instant update
        return;
    }
    
    priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Bought Price (Threshold)',
                    data: boughtPrices,
                    borderColor: '#999999',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    fill: false,
                    pointRadius: 5,
                    pointHoverRadius: 7,
                    pointBackgroundColor: '#999999',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    tension: 0.4,
                    order: 2
                },
                {
                    label: 'Current Price',
                    data: currentPrices,
                    borderColor: avgLineColor,
                    borderWidth: 3,
                    fill: false,
                    pointRadius: 6,
                    pointHoverRadius: 8,
                    pointBackgroundColor: pointColors,
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    tension: 0.4,
                    order: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    align: 'end',
                    labels: {
                        color: '#a0a0b8',
                        font: {
                            size: 11
                        },
                        padding: 15,
                        usePointStyle: true,
                        pointStyle: 'line'
                    }
                },
                tooltip: {
                    backgroundColor: '#1a1a2e',
                    titleColor: '#fff',
                    bodyColor: '#a0a0b8',
                    borderColor: '#2a2a3e',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            const holding = topHoldings[context.dataIndex];
                            const price = context.parsed.y;
                            const pnl = holding.pnl;
                            const pnlPercent = holding.pnl_percent;
                            
                            if (context.datasetIndex === 0) {
                                return `Bought: ₹${price.toFixed(2)}`;
                            } else {
                                return [
                                    `Current: ₹${price.toFixed(2)}`,
                                    `P&L: ${pnl >= 0 ? '+' : ''}₹${pnl.toFixed(2)} (${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%)`,
                                    `Status: ${pnl >= 0 ? '🟢 Profit' : '🔴 Loss'}`
                                ];
                            }
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: '#2a2a3e',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6b6b8c',
                        font: {
                            size: 11
                        }
                    }
                },
                y: {
                    grid: {
                        color: '#2a2a3e',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6b6b8c',
                        callback: function(value) {
                            if (value >= 1000) {
                                return '₹' + (value / 1000).toFixed(1) + 'K';
                            }
                            return '₹' + value.toFixed(0);
                        }
                    }
                }
            },
            interaction: {
                mode: 'index',
                intersect: false
            }
        }
    });
}

// Update P&L chart
function updatePnLChart(holdings) {
    const ctx = document.getElementById('pnlChart').getContext('2d');
    
    // Take top 5 gainers and top 5 losers
    const topGainers = holdings.filter(h => h.pnl > 0).slice(0, 5);
    const topLosers = holdings.filter(h => h.pnl < 0).slice(-5);
    const chartData = [...topGainers, ...topLosers];
    
    const labels = chartData.map(h => h.symbol);
    const data = chartData.map(h => h.pnl);
    const colors = data.map(val => val >= 0 ? '#bfff00' : '#ff1744');
    
    // Update existing chart instead of recreating
    if (pnlChart) {
        pnlChart.data.labels = labels;
        pnlChart.data.datasets[0].data = data;
        pnlChart.data.datasets[0].backgroundColor = colors;
        pnlChart.update('none'); // 'none' animation mode for instant update
        return;
    }
    
    pnlChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'P&L',
                data: data,
                backgroundColor: colors,
                borderRadius: 8,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: '#1a1a2e',
                    titleColor: '#fff',
                    bodyColor: '#a0a0b8',
                    borderColor: '#2a2a3e',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            return `P&L: ₹${formatNumber(context.parsed.y)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#6b6b8c'
                    }
                },
                y: {
                    grid: {
                        color: '#2a2a3e',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6b6b8c',
                        callback: function(value) {
                            return '₹' + (value / 1000).toFixed(1) + 'K';
                        }
                    }
                }
            }
        }
    });
}

// Render individual holding charts
function renderHoldingsCharts() {
    if (!portfolioData || !portfolioData.holdings) return;
    
    const grid = document.getElementById('holdingsGrid');
    const holdings = portfolioData.holdings;
    
    // Check if cards already exist - if so, just update them
    const existingCards = grid.querySelectorAll('.holding-card');
    if (existingCards.length === holdings.length) {
        // Update existing cards instead of recreating
        holdings.forEach((holding, index) => {
            updateHoldingCard(existingCards[index], holding, index);
        });
        return;
    }
    
    // Clear existing cards only if count differs
    grid.innerHTML = '';
    
    // Destroy existing charts
    Object.values(holdingCharts).forEach(chart => chart.destroy());
    holdingCharts = {};
    
    // Create a card for each holding
    holdings.forEach((holding, index) => {
        const chartId = `dashboard-chart-${index}`;
        const isProfitable = holding.pnl >= 0;
        
        const card = document.createElement('div');
        card.className = 'holding-card';
        card.innerHTML = `
            <div class="holding-header">
                <div>
                    <div class="holding-title">${holding.symbol}</div>
                    <div class="holding-qty">Quantity: ${holding.quantity}</div>
                </div>
                <div class="holding-pnl-badge ${isProfitable ? 'profit' : 'loss'}">
                    ${isProfitable ? '+' : ''}${holding.pnl_percent.toFixed(2)}%
                </div>
            </div>
            
            <div class="holding-stats">
                <div class="holding-stat">
                    <div class="holding-stat-label">Bought Price</div>
                    <div class="holding-stat-value">₹${holding.avg_price.toFixed(2)}</div>
                </div>
                <div class="holding-stat">
                    <div class="holding-stat-label">Current Price</div>
                    <div class="holding-stat-value">₹${holding.ltp.toFixed(2)}</div>
                </div>
                <div class="holding-stat">
                    <div class="holding-stat-label">Investment</div>
                    <div class="holding-stat-value">₹${formatNumber(holding.avg_price * holding.quantity)}</div>
                </div>
                <div class="holding-stat">
                    <div class="holding-stat-label">Current Value</div>
                    <div class="holding-stat-value">₹${formatNumber(holding.value)}</div>
                </div>
                <div class="holding-stat">
                    <div class="holding-stat-label">P&L</div>
                    <div class="holding-stat-value ${isProfitable ? 'positive-value' : 'negative-value'}">
                        ${isProfitable ? '+' : ''}₹${formatNumber(holding.pnl)}
                    </div>
                </div>
            </div>
            
            <div class="holding-chart-container">
                <canvas id="${chartId}"></canvas>
            </div>
        `;
        
        grid.appendChild(card);
        
        // Create chart for this holding
        createHoldingChart(chartId, holding);
    });
}

// Update existing holding card without recreating
function updateHoldingCard(card, holding, index) {
    const chartId = `dashboard-chart-${index}`;
    const isProfitable = holding.pnl >= 0;
    
    // Update header
    card.querySelector('.holding-title').textContent = holding.symbol;
    card.querySelector('.holding-qty').textContent = `Quantity: ${holding.quantity}`;
    
    const pnlBadge = card.querySelector('.holding-pnl-badge');
    pnlBadge.className = `holding-pnl-badge ${isProfitable ? 'profit' : 'loss'}`;
    pnlBadge.textContent = `${isProfitable ? '+' : ''}${holding.pnl_percent.toFixed(2)}%`;
    
    // Update stats
    const statValues = card.querySelectorAll('.holding-stat-value');
    statValues[0].textContent = `₹${holding.avg_price.toFixed(2)}`;
    statValues[1].textContent = `₹${holding.ltp.toFixed(2)}`;
    statValues[2].textContent = `₹${formatNumber(holding.avg_price * holding.quantity)}`;
    statValues[3].textContent = `₹${formatNumber(holding.value)}`;
    statValues[4].className = `holding-stat-value ${isProfitable ? 'positive-value' : 'negative-value'}`;
    statValues[4].textContent = `${isProfitable ? '+' : ''}₹${formatNumber(holding.pnl)}`;
    
    // Update chart data if it exists
    updateHoldingChart(chartId, holding);
}

// Update existing holding chart without recreating
function updateHoldingChart(chartId, holding) {
    const chart = holdingCharts[chartId];
    if (!chart) return;
    
    const isProfitable = holding.ltp >= holding.avg_price;
    const lineColor = isProfitable ? '#bfff00' : '#ff1744';
    
    // Update the last data point with current price
    const datasets = chart.data.datasets;
    const dataLength = datasets[1].data.length;
    if (dataLength > 0) {
        datasets[1].data[dataLength - 1] = holding.ltp;
        datasets[1].borderColor = lineColor;
        datasets[1].backgroundColor = isProfitable ? 'rgba(191, 255, 0, 0.1)' : 'rgba(255, 23, 68, 0.1)';
        datasets[1].pointBackgroundColor = lineColor;
        chart.update('none'); // 'none' animation mode for instant update
    }
}

// Create individual chart for a holding
async function createHoldingChart(chartId, holding) {
    const ctx = document.getElementById(chartId).getContext('2d');
    
    // Fetch real historical data
    let labels = [];
    let boughtPrices = [];
    let currentPrices = [];
    
    try {
        const response = await fetch(`/api/historical/${holding.symbol}`);
        const result = await response.json();
        
        if (result.success && result.data && result.data.length > 0) {
            // Use real historical data
            result.data.forEach(record => {
                labels.push(record.time);
                boughtPrices.push(holding.avg_price);
                currentPrices.push(record.close);
            });
        } else {
            // Fallback to last known price if historical data unavailable
            for (let i = 6; i >= 0; i--) {
                const date = new Date();
                date.setDate(date.getDate() - i);
                labels.push(date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
                boughtPrices.push(holding.avg_price);
                currentPrices.push(holding.ltp);
            }
        }
    } catch (error) {
        console.error(`Error fetching historical data for ${holding.symbol}:`, error);
        // Fallback to current price
        for (let i = 6; i >= 0; i--) {
            const date = new Date();
            date.setDate(date.getDate() - i);
            labels.push(date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
            boughtPrices.push(holding.avg_price);
            currentPrices.push(holding.ltp);
        }
    }
    
    const isProfitable = holding.ltp >= holding.avg_price;
    const lineColor = isProfitable ? '#bfff00' : '#ff1744';
    
    holdingCharts[chartId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Bought Price (Threshold)',
                    data: boughtPrices,
                    borderColor: '#999999',
                    backgroundColor: 'rgba(153, 153, 153, 0.05)',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointBackgroundColor: '#999999',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    tension: 0
                },
                {
                    label: 'Market Price',
                    data: currentPrices,
                    borderColor: lineColor,
                    backgroundColor: isProfitable ? 'rgba(191, 255, 0, 0.1)' : 'rgba(255, 23, 68, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    pointBackgroundColor: lineColor,
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    tension: 0.4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: '#0d0d0d',
                    titleColor: '#bfff00',
                    bodyColor: '#ffffff',
                    borderColor: '#bfff00',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            const price = context.parsed.y;
                            if (context.datasetIndex === 0) {
                                return `Threshold: ₹${price.toFixed(2)}`;
                            } else {
                                const diff = price - holding.avg_price;
                                const diffPercent = (diff / holding.avg_price * 100);
                                return [
                                    `Price: ₹${price.toFixed(2)}`,
                                    `Change: ${diff >= 0 ? '+' : ''}₹${diff.toFixed(2)} (${diffPercent >= 0 ? '+' : ''}${diffPercent.toFixed(2)}%)`
                                ];
                            }
                        },
                        labelTextColor: function(context) {
                            if (context.datasetIndex === 0) {
                                return '#999999';
                            }
                            const price = context.parsed.y;
                            const diff = price - holding.avg_price;
                            return diff >= 0 ? '#bfff00' : '#ff1744';
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: '#2a2a3e',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6b6b8c',
                        font: {
                            size: 10
                        }
                    }
                },
                y: {
                    grid: {
                        color: '#2a2a3e',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6b6b8c',
                        font: {
                            size: 10
                        },
                        callback: function(value) {
                            return '₹' + value.toFixed(0);
                        }
                    }
                }
            },
            interaction: {
                mode: 'index',
                intersect: false
            }
        }
    });
}

// Refresh data
function refreshData() {
    fetchPortfolioData();
}

// Format numbers
function formatNumber(num) {
    if (num >= 10000000) {
        return (num / 10000000).toFixed(2) + 'Cr';
    } else if (num >= 100000) {
        return (num / 100000).toFixed(2) + 'L';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(2) + 'K';
    }
    return num.toFixed(2);
}

// Show error
function showError(message) {
    console.error('Error:', message);
    // Could add a toast notification here
}
