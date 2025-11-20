// Positions page JavaScript
let portfolioData = null;

document.addEventListener('DOMContentLoaded', () => {
    updateDateTime();
    fetchPortfolioData();
    setInterval(fetchPortfolioData, 30000);
    setInterval(updateDateTime, 1000);
});

function updateDateTime() {
    const now = new Date();
    const options = { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' };
    document.getElementById('dateDisplay').textContent = now.toLocaleDateString('en-US', options);
}

async function fetchPortfolioData() {
    try {
        const response = await fetch('/api/portfolio');
        const result = await response.json();
        if (result.success && result.data) {
            portfolioData = result.data;
            renderPositions();
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

function renderPositions() {
    if (!portfolioData) return;
    
    const positions = portfolioData.positions || [];
    const summary = document.getElementById('positionsSummary');
    const grid = document.getElementById('positionsGrid');
    
    // Summary
    const totalPnl = positions.reduce((sum, p) => sum + p.pnl, 0);
    const longCount = positions.filter(p => p.type === 'Long').length;
    const shortCount = positions.filter(p => p.type === 'Short').length;
    
    // Check if summary cards already exist - update them instead of re-rendering
    const existingMetricCards = summary.querySelectorAll('.metric-card');
    if (existingMetricCards.length === 4) {
        // Update existing cards
        existingMetricCards[0].querySelector('.metric-value').textContent = positions.length;
        existingMetricCards[1].querySelector('.metric-value').textContent = longCount;
        existingMetricCards[2].querySelector('.metric-value').textContent = shortCount;
        
        const pnlValueEl = existingMetricCards[3].querySelector('.metric-value');
        pnlValueEl.className = `metric-value ${totalPnl >= 0 ? 'positive-value' : 'negative-value'}`;
        pnlValueEl.textContent = `${totalPnl >= 0 ? '+' : ''}₹${formatNumber(totalPnl)}`;
    } else {
        // Create new summary cards
        summary.innerHTML = `
            <div class="metric-card">
                <div class="metric-label">Active Positions</div>
                <div class="metric-value">${positions.length}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Long Positions</div>
                <div class="metric-value">${longCount}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Short Positions</div>
                <div class="metric-value">${shortCount}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total P&L</div>
                <div class="metric-value ${totalPnl >= 0 ? 'positive-value' : 'negative-value'}">
                    ${totalPnl >= 0 ? '+' : ''}₹${formatNumber(totalPnl)}
                </div>
            </div>
        `;
    }
    
    // Positions cards
    if (positions.length === 0) {
        grid.innerHTML = '<div class="table-card"><p style="text-align:center;padding:2rem;color:var(--text-secondary);">No active positions</p></div>';
        return;
    }
    
    // Check if position cards already exist - update them instead of re-rendering
    const existingCards = grid.querySelectorAll('.holding-card');
    if (existingCards.length === positions.length) {
        // Update existing cards
        positions.forEach((pos, index) => {
            updatePositionCard(existingCards[index], pos);
        });
        return;
    }
    
    // Create new position cards
    grid.innerHTML = positions.map(pos => `
        <div class="holding-card">
            <div class="holding-header">
                <div>
                    <div class="holding-title">${pos.symbol}</div>
                    <div class="holding-qty">${pos.type} • Qty: ${Math.abs(pos.quantity)}</div>
                </div>
                <div class="holding-pnl-badge ${pos.pnl >= 0 ? 'profit' : 'loss'}">
                    ${pos.pnl >= 0 ? '+' : ''}₹${formatNumber(pos.pnl)}
                </div>
            </div>
            <div class="holding-stats">
                <div class="holding-stat">
                    <div class="holding-stat-label">Avg Price</div>
                    <div class="holding-stat-value">₹${pos.avg_price.toFixed(2)}</div>
                </div>
                <div class="holding-stat">
                    <div class="holding-stat-label">LTP</div>
                    <div class="holding-stat-value">₹${pos.ltp.toFixed(2)}</div>
                </div>
            </div>
        </div>
    `).join('');
}

// Update existing position card without recreating
function updatePositionCard(card, pos) {
    // Update title and quantity
    card.querySelector('.holding-title').textContent = pos.symbol;
    card.querySelector('.holding-qty').textContent = `${pos.type} • Qty: ${Math.abs(pos.quantity)}`;
    
    // Update P&L badge
    const pnlBadge = card.querySelector('.holding-pnl-badge');
    pnlBadge.className = `holding-pnl-badge ${pos.pnl >= 0 ? 'profit' : 'loss'}`;
    pnlBadge.textContent = `${pos.pnl >= 0 ? '+' : ''}₹${formatNumber(pos.pnl)}`;
    
    // Update stats
    const statValues = card.querySelectorAll('.holding-stat-value');
    statValues[0].textContent = `₹${pos.avg_price.toFixed(2)}`;
    statValues[1].textContent = `₹${pos.ltp.toFixed(2)}`;
}

function refreshData() {
    fetchPortfolioData();
}

function formatNumber(num) {
    if (num >= 10000000) return (num / 10000000).toFixed(2) + 'Cr';
    if (num >= 100000) return (num / 100000).toFixed(2) + 'L';
    if (num >= 1000) return (num / 1000).toFixed(2) + 'K';
    return num.toFixed(2);
}
