import React, { useState } from 'react';

const StrategyCards = ({ strategies, selectedStrategy, onStrategySelect, livePrices, loading }) => {
  const [activeTab, setActiveTab] = useState('overview');
  const getRiskColor = (riskLevel) => {
    switch (riskLevel) {
      case 'low': return 'bg-success-100 text-success-800 border-success-200';
      case 'medium': return 'bg-warning-100 text-warning-800 border-warning-200';
      case 'high': return 'bg-danger-100 text-danger-800 border-danger-200';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 85) return 'text-success-600';
    if (confidence >= 70) return 'text-warning-600';
    return 'text-danger-600';
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatCurrencyDetailed = (amount) => {
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

  if (loading) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-gray-200 rounded w-1/4"></div>
          <div className="space-y-3">
            {[1, 2].map(i => (
              <div key={i} className="h-32 bg-gray-200 rounded-lg"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!strategies.length) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="text-center py-8">
          <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <p className="mt-2 text-gray-600">No strategies available for this segment</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-gray-900">Trading Strategies</h2>
        <span className="text-sm text-gray-600">{strategies.length} strategies</span>
      </div>

      <div className="space-y-4">
        {strategies.map((strategy) => {
          const livePrice = livePrices[strategy.symbol];
          const isSelected = selectedStrategy?.id === strategy.id;
          
          return (
            <div
              key={strategy.id}
              onClick={() => onStrategySelect(strategy)}
              className={`p-6 rounded-lg border-2 transition-all duration-200 cursor-pointer ${
                isSelected
                  ? 'border-primary-500 bg-primary-50 shadow-lg'
                  : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-md'
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <h3 className="text-lg font-semibold text-gray-900">{strategy.symbol}</h3>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium border ${getRiskColor(strategy.riskLevel)}`}>
                      {strategy.riskLevel} risk
                    </span>
                    <span className={`text-sm font-medium ${getConfidenceColor(strategy.confidence)}`}>
                      {strategy.confidence}% confidence
                    </span>
                  </div>
                  <p className="text-gray-600 mb-2">{strategy.name}</p>
                  <p className="text-sm font-medium text-gray-700">{strategy.strategy}</p>
                </div>
                
                <div className="text-right">
                  {livePrice ? (
                    <div>
                      <p className="text-lg font-bold text-gray-900">
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
                      <p className="text-lg font-bold">₹{strategy.entryPrice}</p>
                      <p className="text-sm">Entry Price</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div>
                  <p className="text-xs text-gray-600 mb-1">Capital Required</p>
                  <p className="font-semibold text-gray-900">{formatCurrency(strategy.capitalRequired)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-600 mb-1">Expected Return</p>
                  <p className="font-semibold text-success-600">{strategy.expectedReturn}%</p>
                </div>
                <div>
                  <p className="text-xs text-gray-600 mb-1">Holding Period</p>
                  <p className="font-semibold text-gray-900">{strategy.holdingPeriod}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-600 mb-1">Entry Type</p>
                  <p className="font-semibold text-gray-900 capitalize">{strategy.entryType}</p>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex space-x-1 mb-4 bg-gray-100 rounded-lg p-1">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex-1 flex items-center justify-center space-x-1 py-2 px-2 rounded-md text-xs font-medium transition-colors ${
                      activeTab === tab.id
                        ? 'bg-white text-primary-600 shadow-sm'
                        : 'text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    <span className="text-sm">{tab.icon}</span>
                    <span>{tab.label}</span>
                  </button>
                ))}
              </div>

              {/* Tab Content */}
              <div className="space-y-4">
                {activeTab === 'overview' && (
                  <div className="space-y-3">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">
                        Target: <span className="font-medium text-success-600">{formatCurrencyDetailed(strategy.targetPrice)}</span>
                      </span>
                      <span className="text-gray-600">
                        Stop Loss: <span className="font-medium text-danger-600">{formatCurrencyDetailed(strategy.stopLoss)}</span>
                      </span>
                    </div>
                    
                    {/* Show legs for options strategies */}
                    {strategy.legs && strategy.legs.length > 0 && (
                      <div className="bg-gray-50 rounded-lg p-3">
                        <h4 className="text-sm font-medium text-gray-900 mb-2">Options Legs</h4>
                        <div className="space-y-2">
                          {strategy.legs.map((leg, index) => (
                            <div key={index} className="flex items-center justify-between text-sm">
                              <div className="flex items-center space-x-2">
                                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                  leg.action === 'buy' ? 'bg-success-100 text-success-800' : 'bg-danger-100 text-danger-800'
                                }`}>
                                  {leg.action.toUpperCase()}
                                </span>
                                <span className="text-gray-700">Strike: {formatCurrencyDetailed(leg.strike)}</span>
                              </div>
                              <span className="font-medium text-gray-900">Premium: {formatCurrencyDetailed(leg.premium)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="text-sm text-gray-600">
                      <p><span className="font-medium">Reasoning:</span> {strategy.reasoning}</p>
                    </div>
                  </div>
                )}

                {activeTab === 'technical' && (
                  <div className="space-y-3">
                    <div className="grid grid-cols-1 gap-2">
                      {strategy.technicalIndicators?.map((indicator, index) => (
                        <div key={index} className="p-2 bg-gray-50 rounded text-sm">
                          {indicator}
                        </div>
                      ))}
                    </div>
                    
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      {strategy.marketCap && (
                        <div className="p-2 bg-gray-50 rounded">
                          <p className="text-gray-600">Market Cap</p>
                          <p className="font-medium">{strategy.marketCap}</p>
                        </div>
                      )}
                      {strategy.sector && (
                        <div className="p-2 bg-gray-50 rounded">
                          <p className="text-gray-600">Sector</p>
                          <p className="font-medium">{strategy.sector}</p>
                        </div>
                      )}
                      {strategy.contractSize && (
                        <div className="p-2 bg-gray-50 rounded">
                          <p className="text-gray-600">Contract Size</p>
                          <p className="font-medium">{strategy.contractSize}</p>
                        </div>
                      )}
                      {strategy.expiry && (
                        <div className="p-2 bg-gray-50 rounded">
                          <p className="text-gray-600">Expiry</p>
                          <p className="font-medium">{new Date(strategy.expiry).toLocaleDateString()}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === 'risk' && (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="p-3 bg-gray-50 rounded-lg">
                        <p className="text-xs text-gray-600 mb-1">Risk Level</p>
                        <p className="font-semibold text-gray-900 capitalize">{strategy.riskLevel}</p>
                      </div>
                      <div className="p-3 bg-gray-50 rounded-lg">
                        <p className="text-xs text-gray-600 mb-1">Capital Required</p>
                        <p className="font-semibold text-gray-900">{formatCurrency(strategy.capitalRequired)}</p>
                      </div>
                      <div className="p-3 bg-gray-50 rounded-lg">
                        <p className="text-xs text-gray-600 mb-1">Expected Return</p>
                        <p className="font-semibold text-success-600">{strategy.expectedReturn}%</p>
                      </div>
                      <div className="p-3 bg-gray-50 rounded-lg">
                        <p className="text-xs text-gray-600 mb-1">Holding Period</p>
                        <p className="font-semibold text-gray-900">{strategy.holdingPeriod}</p>
                      </div>
                    </div>
                    
                    <div className="p-3 bg-warning-50 rounded-lg border border-warning-200">
                      <div className="flex items-start space-x-2">
                        <svg className="w-4 h-4 text-warning-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                        </svg>
                        <p className="text-xs text-warning-700">
                          Trading involves risk. Past performance is not indicative of future results.
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Select Strategy Button */}
              <div className="pt-3 border-t border-gray-100">
                <button
                  onClick={() => onStrategySelect(strategy)}
                  className={`w-full py-2 px-4 rounded-lg font-medium transition-colors ${
                    isSelected
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {isSelected ? 'Selected Strategy' : 'Select Strategy'}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default StrategyCards;
