import React from 'react';

const PortfolioSummary = ({ portfolio }) => {
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount || 0);
  };

  const formatPercentage = (value) => {
    const numValue = value || 0;
    return `${numValue >= 0 ? '+' : ''}${numValue.toFixed(2)}%`;
  };

  // Default portfolio data to prevent errors
  const defaultPortfolio = {
    totalCapital: 0,
    utilizedCapital: 0,
    availableCapital: 0,
    totalValue: 0,
    totalPnL: 0,
    totalPnLPercent: 0,
    dayChange: 0,
    dayChangePercent: 0,
  };

  const portfolioData = portfolio || defaultPortfolio;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Portfolio Overview</h2>
        <div className={`px-3 py-1 rounded-full text-sm font-medium ${
          portfolioData.totalPnLPercent >= 0 
            ? 'bg-success-100 text-success-800' 
            : 'bg-danger-100 text-danger-800'
        }`}>
          {formatPercentage(portfolioData.totalPnLPercent)}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div>
          <p className="text-sm text-gray-600 mb-1">Total Capital</p>
          <p className="text-xl font-bold text-gray-900">{formatCurrency(portfolioData.totalCapital)}</p>
        </div>
        <div>
          <p className="text-sm text-gray-600 mb-1">Portfolio Value</p>
          <p className="text-xl font-bold text-gray-900">{formatCurrency(portfolioData.totalValue)}</p>
        </div>
        <div>
          <p className="text-sm text-gray-600 mb-1">Utilized Capital</p>
          <p className="text-lg font-semibold text-gray-900">{formatCurrency(portfolioData.utilizedCapital)}</p>
        </div>
        <div>
          <p className="text-sm text-gray-600 mb-1">Available Capital</p>
          <p className="text-lg font-semibold text-success-600">{formatCurrency(portfolioData.availableCapital)}</p>
        </div>
      </div>

      {/* P&L Section */}
      <div className="bg-gray-50 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600">Total P&L</p>
            <p className={`text-2xl font-bold ${
              portfolioData.totalPnL >= 0 ? 'text-success-600' : 'text-danger-600'
            }`}>
              {formatCurrency(portfolioData.totalPnL)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-600">Day Change</p>
            <p className={`text-lg font-semibold ${
              portfolioData.dayChange >= 0 ? 'text-success-600' : 'text-danger-600'
            }`}>
              {formatCurrency(portfolioData.dayChange)}
            </p>
            <p className={`text-sm ${
              portfolioData.dayChangePercent >= 0 ? 'text-success-600' : 'text-danger-600'
            }`}>
              {formatPercentage(portfolioData.dayChangePercent)}
            </p>
          </div>
        </div>
      </div>

      {/* Capital Utilization Bar */}
      <div className="mt-4">
        <div className="flex justify-between text-sm text-gray-600 mb-2">
          <span>Capital Utilization</span>
          <span>{portfolioData.totalCapital > 0 ? ((portfolioData.utilizedCapital / portfolioData.totalCapital) * 100).toFixed(1) : 0}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-primary-600 h-2 rounded-full transition-all duration-300"
            style={{
              width: `${portfolioData.totalCapital > 0 ? (portfolioData.utilizedCapital / portfolioData.totalCapital) * 100 : 0}%`,
            }}
          ></div>
        </div>
      </div>
    </div>
  );
};

export default PortfolioSummary;
