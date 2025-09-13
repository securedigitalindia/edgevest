import React from 'react';

const ActiveTrades = ({ trades }) => {
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatPrice = (price) => {
    return new Intl.NumberFormat('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(price);
  };

  const getRiskColor = (riskType) => {
    switch (riskType) {
      case 'low': return 'bg-success-100 text-success-800';
      case 'medium': return 'bg-warning-100 text-warning-800';
      case 'high': return 'bg-danger-100 text-danger-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getSegmentColor = (segment) => {
    switch (segment) {
      case 'equity': return 'bg-blue-100 text-blue-800';
      case 'fn0': return 'bg-green-100 text-green-800';
      case 'arbitrage': return 'bg-purple-100 text-purple-800';
      case 'equity + options': return 'bg-orange-100 text-orange-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  if (!trades || trades.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Active Trades</h2>
        <div className="text-center py-8">
          <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <p className="mt-2 text-gray-600">No active trades</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Active Trades</h2>
        <span className="text-sm text-gray-600">{trades.length} active</span>
      </div>

      <div className="space-y-4">
        {trades.map((trade) => (
          <div key={trade.id} className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-3">
                <div>
                  <h3 className="font-semibold text-gray-900">{trade.symbol}</h3>
                  <p className="text-sm text-gray-600">{trade.name}</p>
                </div>
                <div className="flex space-x-2">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getSegmentColor(trade.segment)}`}>
                    {trade.segment}
                  </span>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getRiskColor(trade.riskType)}`}>
                    {trade.riskType} risk
                  </span>
                </div>
              </div>
              <div className="text-right">
                <p className={`text-lg font-bold ${
                  trade.pnl >= 0 ? 'text-success-600' : 'text-danger-600'
                }`}>
                  {formatCurrency(trade.pnl)}
                </p>
                <p className={`text-sm ${
                  trade.pnlPercent >= 0 ? 'text-success-600' : 'text-danger-600'
                }`}>
                  {trade.pnlPercent >= 0 ? '+' : ''}{trade.pnlPercent.toFixed(2)}%
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-gray-600">Entry Price</p>
                <p className="font-medium">{formatPrice(trade.entryPrice)}</p>
              </div>
              <div>
                <p className="text-gray-600">Current Price</p>
                <p className="font-medium">{formatPrice(trade.currentPrice)}</p>
              </div>
              <div>
                <p className="text-gray-600">Target</p>
                <p className="font-medium text-success-600">{formatPrice(trade.targetPrice)}</p>
              </div>
              <div>
                <p className="text-gray-600">Stop Loss</p>
                <p className="font-medium text-danger-600">{formatPrice(trade.stopLoss)}</p>
              </div>
            </div>

            <div className="mt-3 pt-3 border-t border-gray-100">
              <div className="flex justify-between items-center text-sm">
                <div className="flex space-x-4">
                  <span className="text-gray-600">Capital: {formatCurrency(trade.capitalUtilized)}</span>
                  <span className="text-gray-600">R:R: {trade.riskReward}</span>
                  <span className="text-gray-600">Holding: {trade.holdingPeriod}</span>
                </div>
                <div className="flex space-x-2">
                  <button className="px-3 py-1 text-xs bg-primary-100 text-primary-700 rounded-md hover:bg-primary-200 transition-colors">
                    View Details
                  </button>
                  <button className="px-3 py-1 text-xs bg-danger-100 text-danger-700 rounded-md hover:bg-danger-200 transition-colors">
                    Exit Trade
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-gray-200">
        <button className="w-full py-2 text-primary-600 font-medium hover:text-primary-700 transition-colors">
          View All Trades
        </button>
      </div>
    </div>
  );
};

export default ActiveTrades;
