import React, { useState } from 'react';

const StrategyDetails = ({ strategy, livePrice }) => {
  const [activeTab, setActiveTab] = useState('overview');

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(amount);
  };

  const tabs = [
    { id: 'overview', label: 'Overview', icon: '📊' },
    { id: 'technical', label: 'Technical', icon: '📈' },
    { id: 'risk', label: 'Risk', icon: '⚠️' },
  ];

  const getRiskColor = (riskLevel) => {
    switch (riskLevel) {
      case 'low': return 'text-success-600 bg-success-100';
      case 'medium': return 'text-warning-600 bg-warning-100';
      case 'high': return 'text-danger-600 bg-danger-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Selected Strategy: {strategy.symbol}</h2>
          <p className="text-gray-600">{strategy.name} - {strategy.strategy}</p>
        </div>
        <div className="text-right">
          {livePrice ? (
            <div>
              <p className="text-2xl font-bold text-gray-900">
                ₹{livePrice.price.toFixed(2)}
              </p>
              <p className={`text-sm ${
                livePrice.change >= 0 ? 'text-success-600' : 'text-danger-600'
              }`}>
                {livePrice.change >= 0 ? '+' : ''}{livePrice.change.toFixed(2)} 
                ({livePrice.changePercent >= 0 ? '+' : ''}{livePrice.changePercent.toFixed(2)}%)
              </p>
            </div>
          ) : (
            <div className="text-gray-400">
              <p className="text-2xl font-bold">₹{strategy.entryPrice}</p>
              <p className="text-sm">Entry Price</p>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex space-x-1 mb-6 bg-gray-100 rounded-lg p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 flex items-center justify-center space-x-2 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-white text-primary-600 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="space-y-6">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Strategy Info */}
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-600 mb-1">Strategy</p>
                <p className="font-semibold text-gray-900">{strategy.strategy}</p>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-600 mb-1">Risk Level</p>
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${getRiskColor(strategy.riskLevel)}`}>
                  {strategy.riskLevel} risk
                </span>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-600 mb-1">Confidence</p>
                <p className="font-semibold text-gray-900">{strategy.confidence}%</p>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-600 mb-1">Holding Period</p>
                <p className="font-semibold text-gray-900">{strategy.holdingPeriod}</p>
              </div>
            </div>

            {/* Price Levels */}
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Price Levels</h3>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-4 bg-blue-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">Entry Price</p>
                  <p className="text-xl font-bold text-blue-600">{formatCurrency(strategy.entryPrice)}</p>
                  <p className="text-xs text-gray-500 capitalize">{strategy.entryType} order</p>
                </div>
                <div className="text-center p-4 bg-success-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">Target Price</p>
                  <p className="text-xl font-bold text-success-600">{formatCurrency(strategy.targetPrice)}</p>
                  <p className="text-xs text-gray-500">
                    +{(((strategy.targetPrice - strategy.entryPrice) / strategy.entryPrice) * 100).toFixed(1)}%
                  </p>
                </div>
                <div className="text-center p-4 bg-danger-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">Stop Loss</p>
                  <p className="text-xl font-bold text-danger-600">{formatCurrency(strategy.stopLoss)}</p>
                  <p className="text-xs text-gray-500">
                    {(((strategy.stopLoss - strategy.entryPrice) / strategy.entryPrice) * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
            </div>

            {/* Reasoning */}
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-3">Strategy Reasoning</h3>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-gray-700">{strategy.reasoning}</p>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'technical' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Technical Indicators</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {strategy.technicalIndicators?.map((indicator, index) => (
                  <div key={index} className="p-4 bg-gray-50 rounded-lg">
                    <p className="text-sm font-medium text-gray-900">{indicator}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Additional Info */}
            <div className="grid grid-cols-2 gap-4">
              {strategy.marketCap && (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">Market Cap</p>
                  <p className="font-semibold text-gray-900">{strategy.marketCap}</p>
                </div>
              )}
              {strategy.sector && (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">Sector</p>
                  <p className="font-semibold text-gray-900">{strategy.sector}</p>
                </div>
              )}
              {strategy.contractSize && (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">Contract Size</p>
                  <p className="font-semibold text-gray-900">{strategy.contractSize}</p>
                </div>
              )}
              {strategy.expiry && (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600 mb-1">Expiry</p>
                  <p className="font-semibold text-gray-900">{new Date(strategy.expiry).toLocaleDateString()}</p>
                </div>
              )}
            </div>

            {/* Options Legs */}
            {strategy.legs && strategy.legs.length > 0 && (
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Options Legs</h3>
                <div className="space-y-3">
                  {strategy.legs.map((leg, index) => (
                    <div key={index} className="p-4 bg-gray-50 rounded-lg">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            leg.action === 'buy' ? 'bg-success-100 text-success-800' : 'bg-danger-100 text-danger-800'
                          }`}>
                            {leg.action.toUpperCase()}
                          </span>
                          <span className="font-medium">Strike: ₹{leg.strike}</span>
                        </div>
                        <span className="font-semibold">Premium: ₹{leg.premium}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'risk' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-600 mb-1">Risk Level</p>
                <p className="text-xl font-bold text-gray-900 capitalize">{strategy.riskLevel}</p>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-600 mb-1">Capital Required</p>
                <p className="text-xl font-bold text-gray-900">{formatCurrency(strategy.capitalRequired)}</p>
              </div>
            </div>

            <div className="p-4 bg-warning-50 rounded-lg border border-warning-200">
              <div className="flex items-start space-x-3">
                <svg className="w-5 h-5 text-warning-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
                <div>
                  <h4 className="font-medium text-warning-800">Risk Disclaimer</h4>
                  <p className="text-sm text-warning-700 mt-1">
                    Trading involves risk. Past performance is not indicative of future results. 
                    Please ensure you understand the risks before executing any trades.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default StrategyDetails;
