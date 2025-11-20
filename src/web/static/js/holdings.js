// Global state
let portfolioData = null;
let charts = {};
let timelineChart = null;
let portfolioHistory = [];
let selectedTimeframe = '7d'; // Default to 7 days
let isLiveMode = false;
let liveRefreshInterval = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    updateDateTime();
    initTimelineChart();
    fetchPortfolioData();
    fetchPortfolioHistory();
    
    // Auto-refresh every 30 seconds
    setInterval(fetchPortfolioData, 30000);
    setInterval(fetchPortfolioHistory, 30000);
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

// Initialize timeline chart
function initTimelineChart() {
    const ctx = document.getElementById('timelineChart').getContext('2d');
    
    timelineChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Portfolio Value',
                data: [],
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                borderWidth: 3,
                fill: true,
                pointRadius: 0,
                pointHoverRadius: 8,
                pointBackgroundColor: '#bfff00',
                pointBorderColor: '#fff',
                pointBorderWidth: 3,
                tension: 0.4
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
                    backgroundColor: '#0d0d0d',
                    titleColor: '#bfff00',
                    bodyColor: '#ffffff',
                    borderColor: '#6366f1',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            const value = context.parsed.y;
                            return `Value: ₹${formatNumber(value)}`;
                        },
                        afterLabel: function(context) {
                            const dataIndex = context.dataIndex;
                            if (portfolioHistory[dataIndex]) {
                                const pnl = portfolioHistory[dataIndex].pnl;
                                const pnlPercent = portfolioHistory[dataIndex].pnl_percent;
                                return `P&L: ${pnl >= 0 ? '+' : ''}₹${formatNumber(pnl)} (${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%)`;
                            }
                            return '';
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
                        },
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 12
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
                            size: 11
                        },
                        callback: function(value) {
                            return '₹' + formatNumber(value);
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

// Fetch portfolio history for timeline
async function fetchPortfolioHistory() {
    try {
        const response = await fetch('/api/portfolio-history');
        const result = await response.json();
        
        if (result.success && result.data) {
            portfolioHistory = result.data;
            updateTimelineChart();
        }
    } catch (error) {
        console.error('Error fetching portfolio history:', error);
    }
}

// Update timeline chart (without re-rendering entire page)
function updateTimelineChart() {
    if (!timelineChart || portfolioHistory.length === 0) return;
    
    // Extract labels and values with dynamically updated timestamps
    const labels = portfolioHistory.map(h => {
        const date = new Date(h.timestamp);
        // Format time dynamically to show actual timestamp
        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    });
    const values = portfolioHistory.map(h => h.value);
    
    // Update chart data without re-rendering - this updates both time and values
    timelineChart.data.labels = labels;
    timelineChart.data.datasets[0].data = values;
    
    // Update the pointer (last point) to be highlighted
    const pointRadii = new Array(values.length).fill(0);
    if (values.length > 0) {
        pointRadii[pointRadii.length - 1] = 6; // Highlight last point
    }
    timelineChart.data.datasets[0].pointRadius = pointRadii;
    
    // Update chart smoothly without animation for instant update
    timelineChart.update('none'); // 'none' mode = no animation, instant update
    
    // Update info text with current time
    const dataPoints = portfolioHistory.length;
    const duration = dataPoints > 0 ? Math.round((dataPoints * 30) / 60) : 0; // Assuming 30-second intervals
    const now = new Date();
    const lastUpdate = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    document.getElementById('timelineInfo').textContent = `${dataPoints} data points • Last ${duration} minutes • Updated: ${lastUpdate}`;
}

// Fetch portfolio data
async function fetchPortfolioData() {
    console.log('Fetching portfolio data...');
    try {
        const response = await fetch('/api/portfolio');
        const result = await response.json();
        
        if (result.success && result.data) {
            portfolioData = result.data;
            renderHoldings();
        } else {
            console.error('API returned error:', result.message);
        }
    } catch (error) {
        console.error('Error fetching portfolio:', error);
    }
}

// Render holdings cards
function renderHoldings() {
    if (!portfolioData || !portfolioData.holdings) return;
    
    const grid = document.getElementById('holdingsGrid');
    const holdings = portfolioData.holdings;
    
    // Check if cards already exist - if so, just update them
    const existingCards = grid.querySelectorAll('.holding-card');
    if (existingCards.length === holdings.length) {
        // Update existing cards without recreating
        holdings.forEach((holding, index) => {
            updateHoldingCard(existingCards[index], holding, index);
        });
        return;
    }
    
    // Clear existing cards only if count differs
    grid.innerHTML = '';
    
    // Destroy existing charts
    Object.values(charts).forEach(chart => chart.destroy());
    charts = {};
    
    // Create a card for each holding
    holdings.forEach((holding, index) => {
        const isProfitable = holding.pnl >= 0;
        const chartId = `chart-${index}`;
        
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
            
            <div class="holding-chart">
                <canvas id="${chartId}"></canvas>
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
        `;
        
        grid.appendChild(card);
        
        // Create chart after DOM element is added
        setTimeout(() => createHoldingChart(chartId, holding), 0);
    });
}

// Update existing holding card without recreating
function updateHoldingCard(card, holding, index) {
    const chartId = `chart-${index}`;
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
    
    // Update chart data if it exists, otherwise create it
    if (charts[chartId]) {
        updateHoldingChartData(chartId, holding);
    } else {
        // Chart doesn't exist yet, create it
        createHoldingChart(chartId, holding);
    }
}

// Update existing holding chart data without recreating
async function updateHoldingChartData(chartId, holding) {
    const chart = charts[chartId];
    if (!chart) return;
    
    try {
        // Fetch latest data
        const apiUrl = selectedTimeframe === 'live' 
            ? `/api/live/${holding.symbol}`
            : `/api/historical/${holding.symbol}?timeframe=${selectedTimeframe}`;
        
        const response = await fetch(apiUrl);
        const result = await response.json();
        
        if (result.success && result.data && result.data.length > 0) {
            // Update with new data - dynamically update both time labels and values
            const labels = result.data.map(record => {
                // For live mode, always use the actual timestamp from the data
                // This ensures the time updates dynamically on each refresh
                if (selectedTimeframe === 'live') {
                    // Parse the ISO date string and format it to HH:MM
                    const date = new Date(record.date);
                    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
                }
                return record.time;
            });
            const boughtPrices = result.data.map(() => holding.avg_price);
            const currentPrices = result.data.map(record => record.close);
            
            // Update chart data - this will update both time and values
            chart.data.labels = labels;
            chart.data.datasets[0].data = boughtPrices;
            chart.data.datasets[1].data = currentPrices;
            
            // Log live mode time range for debugging
            if (selectedTimeframe === 'live' && result.from_time && result.to_time) {
                const now = new Date();
                console.log(`${holding.symbol} Live data updated at ${now.toLocaleTimeString()}: ${result.from_time} to ${result.to_time} (${result.data.length} points)`);
            }
        } else {
            // Just update the last point with latest price and current time
            const dataLength = chart.data.datasets[1].data.length;
            if (dataLength > 0) {
                // Update the last price
                chart.data.datasets[1].data[dataLength - 1] = holding.ltp;
                
                // Update the last time label to current time (for live mode)
                if (selectedTimeframe === 'live') {
                    const now = new Date();
                    chart.data.labels[dataLength - 1] = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
                }
            }
        }
        
        // Update colors based on profitability
        const isProfitable = holding.ltp >= holding.avg_price;
        const lineColor = isProfitable ? '#bfff00' : '#ff1744';
        
        chart.data.datasets[1].borderColor = lineColor;
        chart.data.datasets[1].backgroundColor = isProfitable ? 'rgba(191, 255, 0, 0.1)' : 'rgba(255, 23, 68, 0.1)';
        chart.data.datasets[1].pointBackgroundColor = lineColor;
        
        // Update chart without animation for smooth refresh
        chart.update('none');
    } catch (error) {
        console.error(`Error updating chart for ${holding.symbol}:`, error);
        // If update fails, just update the last data point
        const dataLength = chart.data.datasets[1].data.length;
        if (dataLength > 0) {
            chart.data.datasets[1].data[dataLength - 1] = holding.ltp;
            // Update time label to current time for live mode
            if (selectedTimeframe === 'live') {
                const now = new Date();
                chart.data.labels[dataLength - 1] = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
            }
            chart.update('none');
        }
    }
}

// Create individual chart for a holding
async function createHoldingChart(chartId, holding) {
    const ctx = document.getElementById(chartId).getContext('2d');
    
    // Fetch historical data based on selected timeframe
    let labels = [];
    let boughtPrices = [];
    let currentPrices = [];
    
    try {
        // Use live endpoint for live mode, otherwise use historical endpoint
        const apiUrl = selectedTimeframe === 'live' 
            ? `/api/live/${holding.symbol}`
            : `/api/historical/${holding.symbol}?timeframe=${selectedTimeframe}`;
        
        const response = await fetch(apiUrl);
        const result = await response.json();
        
        if (result.success && result.data && result.data.length > 0) {
            // Use real intraday data (today's price movements)
            result.data.forEach(record => {
                // For live mode, parse the date to ensure we get the actual timestamp
                if (selectedTimeframe === 'live') {
                    const date = new Date(record.date);
                    labels.push(date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }));
                } else {
                    labels.push(record.time);
                }
                boughtPrices.push(holding.avg_price);
                currentPrices.push(record.close);
            });
        } else {
            // Fallback to current price if historical data unavailable
            // Generate sample intraday labels
            const now = new Date();
            const marketOpen = new Date(now);
            marketOpen.setHours(9, 15, 0, 0);
            
            // Create hourly markers from market open to now
            for (let time = new Date(marketOpen); time <= now; time.setMinutes(time.getMinutes() + 30)) {
                labels.push(time.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }));
                boughtPrices.push(holding.avg_price);
                currentPrices.push(holding.ltp);
            }
        }
    } catch (error) {
        console.error(`Error fetching historical data for ${holding.symbol}:`, error);
        // Fallback to current price with sample times
        const now = new Date();
        const marketOpen = new Date(now);
        marketOpen.setHours(9, 15, 0, 0);
        
        for (let time = new Date(marketOpen); time <= now; time.setMinutes(time.getMinutes() + 30)) {
            labels.push(time.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }));
            boughtPrices.push(holding.avg_price);
            currentPrices.push(holding.ltp);
        }
    }
    
    const isProfitable = holding.ltp >= holding.avg_price;
    const lineColor = isProfitable ? '#bfff00' : '#ff1744';
    
    charts[chartId] = new Chart(ctx, {
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
                        },
                        maxRotation: 45,
                        minRotation: 45,
                        autoSkip: true,
                        maxTicksLimit: 10
                    }
                },
                y: {
                    beginAtZero: false,
                    grid: {
                        color: '#2a2a3e',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6b6b8c',
                        font: {
                            size: 10
                        },
                        maxTicksLimit: 8,
                        callback: function(value) {
                            return '₹' + value.toFixed(2);
                        }
                    },
                    // Dynamic scaling with afterDataLimits callback
                    afterDataLimits: function(scale) {
                        const range = scale.max - scale.min;
                        const padding = Math.max(range * 0.05, 0.5);
                        scale.min = scale.min - padding;
                        scale.max = scale.max + padding;
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

// Change timeframe for stock charts
function changeTimeframe(timeframe) {
    selectedTimeframe = timeframe;
    
    // Update active button state
    document.querySelectorAll('.timeframe-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.timeframe === timeframe) {
            btn.classList.add('active');
        }
    });
    
    // Handle live mode
    if (timeframe === 'live') {
        enableLiveMode();
    } else {
        disableLiveMode();
    }
    
    // Re-render all charts with new timeframe
    renderHoldings();
}

// Enable live mode with auto-refresh
function enableLiveMode() {
    if (isLiveMode) return;
    
    isLiveMode = true;
    const now = new Date();
    console.log(`Live mode enabled at ${now.toLocaleTimeString()} - showing last 10 minutes (1-minute intervals), refreshing every 30 seconds with dynamic time updates`);
    
    // Refresh immediately
    renderHoldings();
    
    // Set up auto-refresh interval (every 30 seconds for live data)
    // This ensures the time labels and values update in real-time
    liveRefreshInterval = setInterval(() => {
        const refreshTime = new Date();
        console.log(`Live mode: auto-refreshing charts at ${refreshTime.toLocaleTimeString()} with dynamically updated time window...`);
        
        // Update all existing charts without full re-render
        if (portfolioData && portfolioData.holdings) {
            portfolioData.holdings.forEach((holding, index) => {
                const chartId = `chart-${index}`;
                if (charts[chartId]) {
                    updateHoldingChartData(chartId, holding);
                }
            });
        }
    }, 30000); // 30 seconds for more responsive live updates
}

// Disable live mode and clear interval
function disableLiveMode() {
    if (!isLiveMode) return;
    
    isLiveMode = false;
    console.log('Live mode disabled');
    
    if (liveRefreshInterval) {
        clearInterval(liveRefreshInterval);
        liveRefreshInterval = null;
    }
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
