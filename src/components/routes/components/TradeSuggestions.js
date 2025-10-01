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
      riskLevel: 'MID',
      holdingPeriod: '7-10 days',
      reasoning: 'Strong quarterly results, technical breakout above resistance',
      shares: 100,
      entryPrice: 1580.00,
    },
    {
      id: 's2',
      symbol: 'NIFTY',
      name: 'Nifty Bull Call Spread',
      segment: 'fno',
      recommendation: 'buy',
      confidence: 88,
      capitalRequired: 25000,
      expectedReturn: 25.0,
      riskLevel: 'MID',
      holdingPeriod: '3-5 days',
      reasoning: 'Bullish momentum with limited downside risk using options spread',
      lots: 1,
      lotSize: 50,
    },
    {
      id: 's3',
      symbol: 'BANKNIFTY',
      name: 'Bank Nifty Protective Put',
      segment: 'fno',
      recommendation: 'buy',
      confidence: 72,
      capitalRequired: 15000,
      expectedReturn: 18.5,
      riskLevel: 'VERY_LOW',
      holdingPeriod: '3-5 days',
      reasoning: 'Downside protection strategy with insurance against market decline',
      lots: 1,
      lotSize: 25,
    },
    {
      id: 's4',
      symbol: 'NIFTY50',
      name: 'Nifty Calendar Spread',
      segment: 'fno',
      recommendation: 'buy',
      confidence: 88,
      capitalRequired: 50000,
      expectedReturn: 8.0,
      riskLevel: 'LOW',
      holdingPeriod: '10-15 days',
      reasoning: 'Time decay strategy exploiting volatility differences across expiry',
      lots: 2,
      lotSize: 50,
    },
    {
      id: 's5',
      symbol: 'NIFTY50-JAN',
      name: 'Nifty 50-Jan Future',
      segment: 'fno',
      recommendation: 'buy',
      confidence: 82,
      capitalRequired: 100000,
      expectedReturn: 15.0,
      riskLevel: 'HIGH',
      holdingPeriod: '3-5 days',
      reasoning: 'Strong uptrend with increasing volume, momentum indicators bullish',
      lots: 1,
      lotSize: 50,
    },
    {
      id: 's6',
      symbol: 'RELIANCE',
      name: 'Reliance Industries Ltd',
      segment: 'equity',
      recommendation: 'buy',
      confidence: 82,
      capitalRequired: 75000,
      expectedReturn: 15.0,
      riskLevel: 'HIGH',
      holdingPeriod: '5-7 days',
      reasoning: 'Trend following strategy with strong momentum indicators',
      shares: 150,
      entryPrice: 2520.75,
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
      case 'VERY_LOW': return 'bg-green-100 text-green-800';
      case 'LOW': return 'bg-green-100 text-green-700';
      case 'MID': return 'bg-yellow-100 text-yellow-800';
      case 'HIGH': return 'bg-red-100 text-red-700';
      case 'VERY_HIGH': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getSegmentColor = (segment) => {
    switch (segment) {
      case 'equity': return 'bg-blue-100 text-blue-800';
      case 'fno': return 'bg-green-100 text-green-800';
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
        <div className="text-sm text-gray-600">
          <span>{suggestions.length} suggestions</span>
          <span className="ml-2 text-green-600">
            ({suggestions.filter(s => s.segment === 'fno').length} F&O)
          </span>
        </div>
      </div>

      <div className="space-y-4">
        {suggestions.map((suggestion) => (
          <div key={suggestion.id} className={`border rounded-lg p-4 hover:shadow-md transition-shadow ${
            suggestion.segment === 'fno' 
              ? 'border-green-200 bg-green-50' 
              : 'border-gray-200'
          }`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-900">{suggestion.symbol}</h3>
                    {suggestion.segment === 'fno' && (
                      <span className="px-2 py-1 bg-green-100 text-green-800 text-xs font-bold rounded">
                        F&O
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600">{suggestion.name}</p>
                </div>
                <div className="flex space-x-2">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getSegmentColor(suggestion.segment)}`}>
                    {suggestion.segment}
                  </span>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getRiskColor(suggestion.riskLevel)}`}>
                    {suggestion.riskLevel.replace('_', ' ')} risk
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

            {/* F&O Lot Information */}
            {suggestion.segment === 'fno' && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-green-600 font-medium text-sm">🎯 F&O Details</span>
                </div>
                

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-gray-600">Lots</p>
                    <p className="font-medium text-green-700">{suggestion.lots || 'N/A'} lot{(suggestion.lots && suggestion.lots > 1) ? 's' : ''}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Lot Size</p>
                    <p className="font-medium text-green-700">{suggestion.lotSize || 'N/A'} units</p>
                  </div>
                </div>
                {suggestion.lots && suggestion.lotSize && (
                  <div className="mt-2 text-xs text-green-600">
                    Total Units: {suggestion.lots * suggestion.lotSize} ({suggestion.lots} × {suggestion.lotSize})
                  </div>
                )}
              </div>
            )}

            {/* Equity Shares Information */}
            {suggestion.segment === 'equity' && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-blue-600 font-medium text-sm">📊 Equity Details</span>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-gray-600">Shares</p>
                    <p className="font-medium text-blue-700">{suggestion.shares || 'N/A'} share{(suggestion.shares && suggestion.shares > 1) ? 's' : ''}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Entry Price</p>
                    <p className="font-medium text-blue-700">{suggestion.entryPrice ? formatCurrency(suggestion.entryPrice) : 'N/A'}</p>
                  </div>
                </div>
              </div>
            )}

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
