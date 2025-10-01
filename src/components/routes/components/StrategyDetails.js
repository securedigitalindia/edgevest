import React from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  Shield, 
  Target, 
  DollarSign, 
  AlertCircle,
  X,
  Info
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


  const currentPnL = calculateCurrentPnL(strategy.legs);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="px-6 py-6 bg-gray-50 border-b border-gray-200 flex justify-between items-start">
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
              </div>
              <div className="flex items-center gap-3 text-sm text-gray-600">
                <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-md text-xs font-medium">
                  {strategy.segment === 'fno' ? strategy.strategyType : strategy.segment.toUpperCase()}
                </span>
                {strategy.legs && strategy.legs.length > 1 && (
                  <span className="px-2 py-1 bg-purple-100 text-purple-700 rounded-md text-xs font-medium">
                    {strategy.legs.length} Legs
                  </span>
                )}
                <span className={`px-2 py-1 rounded-md text-xs font-medium ${
                  strategy.status === 'active' 
                    ? 'bg-green-100 text-green-700' 
                    : 'bg-red-100 text-red-700'
                }`}>
                  {strategy.status === 'active' ? 'ACTIVE' : 'CLOSED'}
                </span>
                <span 
                  className="px-2 py-1 rounded-md text-xs font-medium bg-orange-100 text-orange-700 cursor-help flex items-center gap-1"
                  title={`Holding Period: ${strategy.holdingPeriod}`}
                >
                  {strategy.holdingPeriod.includes('7-30') || strategy.holdingPeriod.includes('short') ? 'SHORT TERM' :
                   strategy.holdingPeriod.includes('30-90') || strategy.holdingPeriod.includes('mid') ? 'MID TERM' :
                   strategy.holdingPeriod.includes('90+') || strategy.holdingPeriod.includes('long') ? 'LONG TERM' :
                   'MID TERM'}
                  <Info size={10} />
                </span>
              </div>
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
             <div className="flex items-center justify-between mb-4">
               <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                 Strategy Legs
               </h3>
               <div className="text-sm">
                 <span className="text-gray-600">P&L: </span>
                 <span className={`font-semibold ${
                   currentPnL >= 0 ? 'text-green-600' : 'text-red-600'
                 }`}>
                   {currentPnL >= 0 ? '+' : ''}{formatCurrency(Math.abs(currentPnL))}
                 </span>
               </div>
             </div>
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
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Trade Details
                </h3>
                <div className="text-sm">
                  <span className="text-gray-600">Total P&L: </span>
                  <span className={`font-semibold ${
                    currentPnL >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {currentPnL >= 0 ? '+' : ''}{formatCurrency(Math.abs(currentPnL))}
                  </span>
                </div>
              </div>
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
                </div>
            </div>
          </div>
        )}

         {/* Capital & Risk | Targets & Stop Loss - Unified Section */}
         <div className="px-6 py-6">
           <div className="border border-gray-200 rounded-xl overflow-hidden">
             <button className="w-full px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left">
               <div className="flex items-center justify-between">
                 <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                   <DollarSign size={16} />
                   Capital & Risk | Targets & Stop Loss
                 </h3>
                 <svg className="w-5 h-5 text-gray-500 transform transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                 </svg>
               </div>
             </button>
             <div className="p-4 bg-white">
               
               {/* Capital & Risk Section */}
               <div className="mb-6">
                 <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-3 flex items-center gap-2">
                   <DollarSign size={14} />
                   Capital & Risk
                 </h4>
                 
                 {/* Capital Required - Highlighted */}
                 <div className="mb-4 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-200">
                   <div className="flex items-center justify-between">
                     <div>
                       <div className="text-sm text-gray-600 mb-1">Capital Required</div>
                       <div className="text-2xl font-bold text-gray-900">
                         {strategy.id.includes('eq_') ? 'Flexible' : formatCurrency(Math.abs(strategy.capitalRequired))}
                       </div>
                     </div>
                     <div className="text-right">
                       <div className="text-xs text-gray-500">Risk Level</div>
                       <div className="text-lg font-bold" style={{ color: getRiskColor(strategy.riskLevel) }}>
                         {strategy.riskLevel}
                       </div>
                     </div>
                   </div>
                 </div>

                 {/* Risk Metrics */}
                 <div className="grid grid-cols-2 gap-3 mb-3">
                   <div className="p-3 bg-blue-50 rounded-lg border border-blue-200 text-center">
                     <div className="text-xs text-gray-600 mb-1">Confidence</div>
                     <div className="text-lg font-bold text-blue-600">
                       {strategy.confidence || 85}%
                     </div>
                   </div>
                   <div className="p-3 bg-gray-50 rounded-lg border border-gray-200 text-center">
                     <div className="text-xs text-gray-600 mb-1">Risk:Reward</div>
                     <div className="text-lg font-bold text-gray-900">
                       {strategy.riskReward || '1:2'}
                     </div>
                   </div>
                 </div>
                 
               </div>

               {/* Targets & Stop Loss Section */}
               <div>
                 <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-3 flex items-center gap-2">
                   <Target size={14} />
                   Targets & Stop Loss
                 </h4>
                 
                 <div className="grid grid-cols-2 gap-3">
                   {/* Target Price */}
                   <div 
                     className="p-4 rounded-xl border"
                     style={{ 
                       background: 'linear-gradient(135deg, #10b98110 0%, #10b98105 100%)',
                       borderColor: '#10b98120'
                     }}
                   >
                     <div className="flex items-center gap-2 mb-2">
                       <Target size={14} color="#10b981" />
                       <span className="text-xs font-semibold text-gray-900">Target</span>
                     </div>
                     <div className="text-lg font-bold text-gray-900 mb-1">
                       {formatCurrencyDetailed(strategy.targetPrice)}
                     </div>
                     <div className="text-sm font-bold text-green-600">
                       +{formatCurrency((strategy.targetPrice - strategy.entryPrice) * 50)}
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
                       <Shield size={14} color="#ef4444" />
                       <span className="text-xs font-semibold text-gray-900">Stop Loss</span>
                     </div>
                     <div className="text-lg font-bold text-gray-900 mb-1">
                       {formatCurrencyDetailed(strategy.stopLoss)}
                     </div>
                     <div className="text-sm font-bold text-red-600">
                       -{formatCurrency(strategy.capitalRequired * 0.3)}
                     </div>
                   </div>
                 </div>

                 {/* Max Profit & Max Loss */}
                 <div className="grid grid-cols-2 gap-3 mt-3">
                   <div className="p-3 bg-green-50 rounded-lg border border-green-200 text-center">
                     <div className="text-xs text-gray-600 mb-1">Max Profit</div>
                     <div className="text-lg font-bold text-green-600">
                       +{formatCurrency(strategy.maxProfit || strategy.expectedReturn * 1000)}
                     </div>
                   </div>
                   
                   <div className="p-3 bg-red-50 rounded-lg border border-red-200 text-center">
                     <div className="text-xs text-gray-600 mb-1">Max Loss</div>
                     <div className="text-lg font-bold text-red-600">
                       -{formatCurrency(strategy.maxLoss || strategy.capitalRequired * 0.5)}
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
              <span className="text-sm font-medium">View Details</span>
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