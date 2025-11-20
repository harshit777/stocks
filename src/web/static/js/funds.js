// Funds page JavaScript  
let fundsData = null;

document.addEventListener('DOMContentLoaded', () => {
    updateDateTime();
    fetchFundsData();
    setInterval(fetchFundsData, 30000);
    setInterval(updateDateTime, 1000);
});

function updateDateTime() {
    const now = new Date();
    const options = { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' };
    document.getElementById('dateDisplay').textContent = now.toLocaleDateString('en-US', options);
}

async function fetchFundsData() {
    try {
        const response = await fetch('/api/funds');
        const result = await response.json();
        if (result.success && result.data) {
            fundsData = result.data;
            renderFunds();
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

function renderFunds() {
    if (!fundsData) return;
    
    const overview = document.getElementById('fundsOverview');
    
    overview.innerHTML = `
        <div class="metric-card">
            <div class="metric-label">💰 Available Cash</div>
            <div class="metric-value" style="color: #bfff00;">₹${formatNumber(fundsData.available_cash)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">📊 Available Margin</div>
            <div class="metric-value" style="color: #bfff00;">₹${formatNumber(fundsData.available_margin)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">📉 Used Margin</div>
            <div class="metric-value" style="color: #ff1744;">₹${formatNumber(fundsData.used_margin)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">🏦 Opening Balance</div>
            <div class="metric-value" style="color: ${fundsData.opening_balance >= 0 ? '#bfff00' : '#ff1744'};">₹${formatNumber(fundsData.opening_balance)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">💎 Collateral</div>
            <div class="metric-value" style="color: #bfff00;">₹${formatNumber(fundsData.collateral)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">💸 Payin</div>
            <div class="metric-value" style="color: ${fundsData.payin >= 0 ? '#bfff00' : '#ff1744'};">₹${formatNumber(fundsData.payin)}</div>
        </div>
    `;
}

function refreshData() {
    fetchFundsData();
}

function formatNumber(num) {
    if (num >= 10000000) return (num / 10000000).toFixed(2) + 'Cr';
    if (num >= 100000) return (num / 100000).toFixed(2) + 'L';
    if (num >= 1000) return (num / 1000).toFixed(2) + 'K';
    return num.toFixed(2);
}
