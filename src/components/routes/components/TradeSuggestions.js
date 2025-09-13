import React from 'react';

const TradeSuggestions = () => {
  // Mock trade suggestions - in real app, this would come from the service
  const suggestions = [
    {
      id: 's1',
      symbol: 'INFY',
      name: 'Infosys Ltd',
      segment: 'equity',
      recommendation: 'buy',
      confidence: 85,
      capitalRequired: 50000,
      expectedReturn: 12.5,
      riskLevel: 'medium',
      holdingPeriod: '7-10 days',
      reasoning: 'Strong quarterly results, technical breakout above resistance',
    },
    {
      id: 's2',
      symbol: 'BANKNIFTY',
      name: 'Bank Nifty',
      segment: 'arbitrage',
      recommendation: 'buy',
      confidence: 92,
      capitalRequired: 100000,
      expectedReturn: 8.5,
      riskLevel: 'low',
      holdingPeriod: '1-2 days',
      reasoning: 'Arbitrage opportunity between spot and futures',
    },
  ];

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const getRiskColor = (riskLevel) => {
    switch (riskLevel) {
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

  const getRecommendationColor = (recommendation) => {
    switch (recommendation) {
      case 'buy': return 'bg-success-600 text-white';
      case 'sell': return 'bg-danger-600 text-white';
      case 'hold': return 'bg-warning-600 text-white';
      default: return 'bg-gray-600 text-white';
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Smart Trade Suggestions</h2>
        <span className="text-sm text-gray-600">{suggestions.length} suggestions</span>
      </div>

      <div className="space-y-4">
        {suggestions.map((suggestion) => (
          <div key={suggestion.id} className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-3">
                <div>
                  <h3 className="font-semibold text-gray-900">{suggestion.symbol}</h3>
                  <p className="text-sm text-gray-600">{suggestion.name}</p>
                </div>
                <div className="flex space-x-2">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getSegmentColor(suggestion.segment)}`}>
                    {suggestion.segment}
                  </span>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getRiskColor(suggestion.riskLevel)}`}>
                    {suggestion.riskLevel} risk
                  </span>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <span className={`px-3 py-1 rounded-full text-xs font-medium ${getRecommendationColor(suggestion.recommendation)}`}>
                  {suggestion.recommendation.toUpperCase()}
                </span>
                <div className="text-right">
                  <p className="text-sm font-medium text-gray-900">{suggestion.confidence}% confidence</p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4 text-sm mb-3">
              <div>
                <p className="text-gray-600">Capital Required</p>
                <p className="font-medium">{formatCurrency(suggestion.capitalRequired)}</p>
              </div>
              <div>
                <p className="text-gray-600">Expected Return</p>
                <p className="font-medium text-success-600">{suggestion.expectedReturn}%</p>
              </div>
              <div>
                <p className="text-gray-600">Holding Period</p>
                <p className="font-medium">{suggestion.holdingPeriod}</p>
              </div>
            </div>

            <div className="mb-3">
              <p className="text-sm text-gray-600 mb-1">Reasoning</p>
              <p className="text-sm text-gray-700">{suggestion.reasoning}</p>
            </div>

            <div className="flex space-x-2">
              <button className="flex-1 py-2 px-4 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors font-medium">
                Execute Trade
              </button>
              <button className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                Analyze
              </button>
              <button className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                Dismiss
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-gray-200">
        <button className="w-full py-2 text-primary-600 font-medium hover:text-primary-700 transition-colors">
          View All Suggestions
        </button>
      </div>
    </div>
  );
};

export default TradeSuggestions;
