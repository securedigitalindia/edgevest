import React from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  Shield, 
  Target, 
  DollarSign, 
  BarChart3, 
  Clock, 
  AlertCircle,
  Layers,
  X
} from 'lucide-react';

const StrategyDetails = ({ strategy, onClose }) => {

  if (!strategy) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
        <div className="bg-white rounded-2xl max-w-md w-full p-6 text-center">
          <p className="text-gray-600">No strategy selected</p>
          <button 
            onClick={onClose}
            className="mt-4 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

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


  const currentPnL = calculateCurrentPnL(strategy.legs);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="px-6 py-6 bg-gradient-to-r from-gray-50 to-gray-100 border-b border-gray-200 flex justify-between items-start">
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
            </div>
            <p className="text-gray-600 text-sm leading-relaxed">
              {strategy.reasoning || `${strategy.segment} strategy with ${strategy.expectedReturn}% expected return`}
            </p>
          </div>
          
          <button 
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X size={20} />
          </button>
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
            onClick={onClose}
            className="px-6 py-3 bg-gradient-to-r from-gray-600 to-gray-700 text-white rounded-lg font-semibold text-sm hover:from-gray-700 hover:to-gray-800 transition-all shadow-md"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default StrategyDetails;