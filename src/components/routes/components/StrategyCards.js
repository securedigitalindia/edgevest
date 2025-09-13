import React from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  Shield, 
  Zap, 
  Target, 
  DollarSign, 
  BarChart3, 
  Clock, 
  Plus, 
  AlertCircle,
  Layers,
  Play,
  Square,
} from 'lucide-react';

const StrategyCards = ({ strategies, selectedStrategy, onStrategySelect, onAddToPortfolio }) => {

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatCurrencyDetailed = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  };

  const getSegmentColor = (segment) => {
    const colors = {
      'Equity': '#10b981',
      'Futures': '#3b82f6',
      'Options': '#8b5cf6',
      'F&O': '#8b5cf6'
    };
    return colors[segment] || '#6b7280';
  };

  const getRiskColor = (risk) => {
    const colors = {
      'LOW': '#10b981',
      'MEDIUM': '#f59e0b',
      'HIGH': '#ef4444'
    };
    return colors[risk] || '#6b7280';
  };

  const getActionColor = (action) => {
    return action === 'buy' ? '#10b981' : '#ef4444';
  };

  const calculateCurrentPnL = (legs) => {
    if (!legs) return 0;
    return legs.reduce((total, leg) => {
      const pnl = (leg.currentPrice - leg.entryPrice) * leg.quantity * (leg.action === 'buy' ? 1 : -1);
      return total + pnl;
    }, 0);
  };


  if (!strategies || strategies.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-gray-400 mb-4">
          <svg className="mx-auto h-16 w-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        </div>
        <p className="text-gray-600 text-lg">No strategies available</p>
        <p className="text-gray-500 text-sm">Select a trading segment to view strategies</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {strategies.map((strategy) => {
        const currentPnL = calculateCurrentPnL(strategy.legs);
        const isSelected = selectedStrategy?.id === strategy.id;
        
        return (
          <div 
            key={strategy.id} 
            className={`bg-white rounded-2xl overflow-hidden shadow-lg transition-all duration-200 ${
              isSelected ? 'ring-2 ring-primary-500 shadow-xl' : 'hover:shadow-xl'
            }`}
          >
            {/* Strategy Header */}
            <div className="px-6 py-6 bg-gradient-to-r from-gray-50 to-gray-100 border-b border-gray-200">
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                    <h2 className="text-2xl font-bold text-gray-900">
                      {strategy.strategy}
                    </h2>
                    <span 
                      className="px-3 py-1 rounded-lg text-xs font-semibold"
                      style={{ 
                        background: getSegmentColor(strategy.segment) + '20',
                        color: getSegmentColor(strategy.segment)
                      }}
                    >
                      {strategy.strategyType || strategy.segment}
                    </span>
                    {strategy.legs && strategy.legs.length > 1 && (
                      <span className="px-3 py-1 bg-indigo-100 text-indigo-600 rounded-lg text-xs font-medium flex items-center gap-1">
                        <Layers size={12} />
                        {strategy.legs.length} Legs
                      </span>
                    )}
                    <span className={`px-3 py-1 rounded-lg text-xs font-medium flex items-center gap-1 ${
                      strategy.status === 'active' 
                        ? 'bg-green-100 text-green-700' 
                        : 'bg-gray-100 text-gray-700'
                    }`}>
                      {strategy.status === 'active' ? <Play size={12} /> : <Square size={12} />}
                      {strategy.status === 'active' ? 'Active' : 'Closed'}
                    </span>
                  </div>
                  <p className="text-gray-600 text-sm leading-relaxed">
                    {strategy.reasoning || `${strategy.segment} strategy with ${strategy.expectedReturn}% expected return`}
                  </p>
                </div>
                
                <div className="flex flex-col items-end gap-2">
                  <div className="flex items-center gap-2">
                    <Shield size={16} color={getRiskColor(strategy.riskLevel)} />
                    <span 
                      className="text-sm font-semibold"
                      style={{ color: getRiskColor(strategy.riskLevel) }}
                    >
                      {strategy.riskLevel} RISK
                    </span>
                  </div>
                  <div className="flex items-center gap-1 px-2 py-1 bg-gray-100 rounded-md">
                    <Zap size={12} color="#6b7280" />
                    <span className="text-xs text-gray-600">
                      Confidence: <span className="font-semibold text-gray-900">{strategy.confidence || 85}%</span>
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Strategy Details - Only for Options with Legs */}
            {strategy.legs && strategy.legs.length > 0 && (
              <div className="px-6 py-6 border-b border-gray-200">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
                  Strategy Legs
                </h3>
                <div className="space-y-3">
                  {strategy.legs.map((leg, index) => (
                    <div key={index} className="flex items-center p-4 bg-gray-50 rounded-xl border border-gray-200">
                      <div 
                        className="w-8 h-8 rounded-lg flex items-center justify-center mr-4"
                        style={{ background: getActionColor(leg.action) + '20' }}
                      >
                        {leg.action === 'buy' ? 
                          <TrendingUp size={16} color={getActionColor(leg.action)} /> :
                          <TrendingDown size={16} color={getActionColor(leg.action)} />
                        }
                      </div>
                      
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-semibold text-gray-900 text-base">
                            {leg.action.toUpperCase()} {strategy.symbol || 'INSTRUMENT'}
                          </span>
                          <span className="text-xs text-gray-500 bg-gray-200 px-2 py-1 rounded">
                            Qty: {leg.quantity || 1}
                          </span>
                        </div>
                        <div className="flex gap-5 text-sm">
                          <span className="text-gray-600">
                            Entry: <span className="font-semibold text-gray-900">{formatCurrencyDetailed(leg.entryPrice || strategy.entryPrice)}</span>
                          </span>
                          <span className="text-gray-600">
                            Current: <span className={`font-semibold ${
                              (leg.currentPrice || strategy.currentPrice) >= (leg.entryPrice || strategy.entryPrice) 
                                ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {formatCurrencyDetailed(leg.currentPrice || strategy.currentPrice)}
                            </span>
                          </span>
                          <span className="text-gray-600">
                            P&L: <span className={`font-semibold ${
                              currentPnL >= 0 ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {currentPnL >= 0 ? '+' : ''}{formatCurrency(Math.abs(currentPnL))}
                            </span>
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Trade Details - For Equity and Futures */}
            {(!strategy.legs || strategy.legs.length === 0) && (
              <div className="px-6 py-6 border-b border-gray-200">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
                  Trade Details
                </h3>
                <div className="p-4 bg-gray-50 rounded-xl border border-gray-200">
                  <div className="flex items-center gap-3 mb-3">
                    <div 
                      className="w-8 h-8 rounded-lg flex items-center justify-center"
                      style={{ background: getSegmentColor(strategy.segment) + '20' }}
                    >
                      <TrendingUp size={16} color={getSegmentColor(strategy.segment)} />
                    </div>
                    <div>
                      <div className="font-semibold text-gray-900 text-base">
                        {strategy.id.includes('eq_') ? 'BUY' : strategy.id.includes('ft_') ? 'BUY FUT' : 'BUY OPT'} {strategy.symbol}
                      </div>
                      <div className="text-sm text-gray-600">{strategy.name}</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-600">Entry Price:</span>
                      <div className="font-semibold text-gray-900">{formatCurrencyDetailed(strategy.entryPrice)}</div>
                    </div>
                    <div>
                      <span className="text-gray-600">Current Price:</span>
                      <div className={`font-semibold ${
                        strategy.currentPrice >= strategy.entryPrice ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {formatCurrencyDetailed(strategy.currentPrice)}
                      </div>
                    </div>
                    <div>
                      <span className="text-gray-600">Change:</span>
                      <div className={`font-semibold ${
                        strategy.currentPrice >= strategy.entryPrice ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {strategy.currentPrice >= strategy.entryPrice ? '+' : ''}{formatCurrencyDetailed(strategy.currentPrice - strategy.entryPrice)}
                      </div>
                    </div>
                    <div>
                      <span className="text-gray-600">Change %:</span>
                      <div className={`font-semibold ${
                        strategy.currentPrice >= strategy.entryPrice ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {strategy.currentPrice >= strategy.entryPrice ? '+' : ''}{(((strategy.currentPrice - strategy.entryPrice) / strategy.entryPrice) * 100).toFixed(2)}%
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Capital & Risk and Targets Section */}
            <div className="px-6 py-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Capital and Risk Info */}
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
                  Capital & Risk
                </h3>
                
                <div className="space-y-3">
                  <div 
                    className="p-4 rounded-xl border"
                    style={{ 
                      background: 'linear-gradient(135deg, #6366f110 0%, #6366f105 100%)',
                      borderColor: '#6366f120'
                    }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <DollarSign size={16} color="#6366f1" />
                      <span className="text-xs text-gray-600 font-medium">Capital Required</span>
                    </div>
                    <div className="text-2xl font-bold text-gray-900">
                      {strategy.id.includes('eq_') ? 'Flexible' : formatCurrency(Math.abs(strategy.capitalRequired))}
                    </div>
                    <div className="text-xs text-gray-600 mt-1">
                      Current P&L: <span className={`font-semibold ${
                        currentPnL >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {currentPnL >= 0 ? '+' : ''}{formatCurrency(Math.abs(currentPnL))}
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 bg-green-50 rounded-lg border border-green-200">
                      <div className="text-xs text-gray-600 mb-1">Max Profit</div>
                      <div className="text-lg font-bold text-green-600">
                        +{formatCurrency(strategy.maxProfit || strategy.expectedReturn * 1000)}
                      </div>
                    </div>
                    
                    <div className="p-3 bg-red-50 rounded-lg border border-red-200">
                      <div className="text-xs text-gray-600 mb-1">Max Loss</div>
                      <div className="text-lg font-bold text-red-600">
                        -{formatCurrency(strategy.maxLoss || strategy.capitalRequired * 0.5)}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                      <div className="text-xs text-gray-600 mb-1 flex items-center gap-1">
                        <BarChart3 size={12} />
                        Risk:Reward
                      </div>
                      <div className="text-lg font-bold text-yellow-600">
                        {strategy.riskReward || '1:2'}
                      </div>
                    </div>
                    
                    <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                      <div className="text-xs text-gray-600 mb-1 flex items-center gap-1">
                        <Clock size={12} />
                        Holding
                      </div>
                      <div className="text-lg font-bold text-gray-900">
                        {strategy.holdingPeriod}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Targets Section */}
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
                  Targets & Stop Loss
                </h3>
                
                <div className="space-y-2">

                  {/* Selected Target Details */}
                  <div 
                    className="p-4 rounded-xl border"
                    style={{ 
                      background: 'linear-gradient(135deg, #10b98110 0%, #10b98105 100%)',
                      borderColor: '#10b98120'
                    }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <Target size={16} color="#10b981" />
                      <span className="text-sm font-semibold text-gray-900">
                        Target Price
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-gray-600">Level</div>
                        <div className="text-lg font-bold text-gray-900">
                          {formatCurrencyDetailed(strategy.targetPrice)}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-600">Profit</div>
                        <div className="text-lg font-bold text-green-600">
                          +{formatCurrency((strategy.targetPrice - strategy.entryPrice) * 50)}
                        </div>
                      </div>
                    </div>
                    <div className="mt-2 p-2 bg-green-50 rounded-md">
                        <span className="text-xs text-gray-600">
                          Expected Return: <span className="font-semibold text-green-600">{strategy.expectedReturn}%</span>
                        </span>
                    </div>
                  </div>

                  {/* Stop Loss */}
                  <div 
                    className="p-4 rounded-xl border"
                    style={{ 
                      background: 'linear-gradient(135deg, #ef444410 0%, #ef444405 100%)',
                      borderColor: '#ef444420'
                    }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <Shield size={16} color="#ef4444" />
                      <span className="text-sm font-semibold text-gray-900">Stop Loss</span>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-gray-600">Level</div>
                        <div className="text-lg font-bold text-gray-900">
                          {formatCurrencyDetailed(strategy.stopLoss)}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-600">Max Loss</div>
                        <div className="text-lg font-bold text-red-600">
                          -{formatCurrency(strategy.capitalRequired * 0.3)}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Footer */}
            <div className="px-6 py-5 bg-gray-50 border-t border-gray-200 flex justify-between items-center">
              <div className="flex gap-3">
                <button className="flex items-center gap-2 px-4 py-2 text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors">
                  <AlertCircle size={14} />
                  <span className="text-sm font-medium">View Analysis</span>
                </button>
              </div>
              
              <button
                onClick={() => onAddToPortfolio(strategy)}
                className={`flex items-center gap-2 px-6 py-3 rounded-lg font-semibold text-sm transition-all ${
                  isSelected
                    ? 'bg-gradient-to-r from-primary-500 to-primary-600 text-white shadow-lg'
                    : 'bg-gradient-to-r from-gray-600 to-gray-700 text-white hover:from-gray-700 hover:to-gray-800 shadow-md'
                }`}
              >
                <Plus size={16} />
                Add to Portfolio
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default StrategyCards;