import React, { useState, useEffect } from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  Shield, 
  Target, 
  DollarSign, 
  Plus,
  Info,
  X
} from 'lucide-react';
import ShareTradeButton from '../../common/ShareTradeButton';
import AddToPortfolioModal from '../../common/AddToPortfolioModal';

const StrategyCards = ({ strategies, selectedStrategy, onStrategySelect, onAddToPortfolio, generateTradeUrl }) => {
  const [showDetailsModal, setShowDetailsModal] = useState(null);
  const [showAddToPortfolioModal, setShowAddToPortfolioModal] = useState(null);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (showDetailsModal || showAddToPortfolioModal) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    
    // Cleanup on unmount
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [showDetailsModal, showAddToPortfolioModal]);

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

  // Calculate P&L based on segment and status
  const calculatePnL = (strategy) => {
    const isActive = strategy.status === 'active';
    const entryPrice = strategy.entryPrice;

    if (strategy.segment === 'equity') {
      // Equity: For active use currentPrice, for closed use exitPrice
      const price = isActive ? strategy.currentPrice : (strategy.exitPrice || strategy.currentPrice);
      const lotSize = 1; // Keep lot size as 1 for equity
      return (price - entryPrice) * lotSize;
    } else if (strategy.segment === 'fno' && strategy.strategyType === 'Futures') {
      // Futures: Sum of all legs P&L (similar to Options)
      if (!strategy.legs || strategy.legs.length === 0) return 0;
      
      return strategy.legs.reduce((total, leg) => {
        const legCurrentPrice = isActive ? (leg.currentPrice || strategy.currentPrice) : (leg.exitPrice || leg.currentPrice || strategy.currentPrice);
        const legEntryPrice = leg.entryPrice || strategy.entryPrice;
        const lotSize = leg.lotSize || strategy.contractSize || 1;
        const quantity = leg.quantity || 1;
        
        // For futures: (current/exit - entry) * lot size * quantity
        // For sell actions, reverse the P&L calculation (short position)
        const priceDiff = legCurrentPrice - legEntryPrice;
        const legPnL = (leg.action === 'sell' ? -priceDiff : priceDiff) * lotSize * quantity;
        return total + legPnL;
      }, 0);
    } else if (strategy.segment === 'fno' && (strategy.strategyType === 'Options' || strategy.strategyType === 'Hybrid')) {
      // Options: Sum of all legs P&L
      if (!strategy.legs || strategy.legs.length === 0) return 0;
      
      return strategy.legs.reduce((total, leg) => {
        const legCurrentPrice = isActive ? (leg.currentPrice || strategy.currentPrice) : (leg.exitPrice || leg.currentPrice || strategy.currentPrice);
        const legEntryPrice = leg.entryPrice || strategy.entryPrice;
        const lotSize = leg.lotSize || strategy.contractSize || 1;
        const quantity = leg.quantity || 1;
        
        // For options: (current/exit - entry) * lot size * quantity
        // For sell actions, we need to reverse the P&L calculation
        const priceDiff = legCurrentPrice - legEntryPrice;
        const legPnL = (leg.action === 'sell' ? -priceDiff : priceDiff) * lotSize * quantity;
        return total + legPnL;
      }, 0);
    }
    
    return 0;
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
        <p className="text-gray-500 text-sm">Try switching between Active and Closed trades</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {strategies.map((strategy) => {
        try {
          const currentPnL = calculatePnL(strategy);
          const isSelected = selectedStrategy?.id === strategy.id;
        
        return (
          <div 
            key={strategy.id}
            id={`trade-${strategy.id}`}
            className={`bg-white rounded-2xl overflow-hidden shadow-lg transition-all duration-200 ${
              isSelected ? 'ring-2 ring-primary-500 shadow-xl' : 'hover:shadow-xl'
            }`}
          >
            {/* Strategy Header */}
            <div className="px-4 py-4 bg-gradient-to-r from-gray-100 to-gray-200 border-b border-gray-300">
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <h2 className="text-lg font-bold text-gray-900">
                      {strategy.strategy}
                    </h2>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-gray-600 flex-wrap">
                    {/* 1. Status */}
                    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                      strategy.status === 'active' 
                        ? 'bg-green-100 text-green-700' 
                        : 'bg-red-100 text-red-700'
                    }`}>
                      {strategy.status === 'active' ? 'ACTIVE' : 'CLOSED'}
                    </span>
                    
                    {/* 2. Strategy Type */}
                    <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                      {strategy.segment === 'fno' 
                        ? `${(strategy.strategyType || '').toUpperCase()}${strategy.legs && strategy.legs.length > 1 ? ` (${strategy.legs.length} LEGS)` : ''}`
                        : (strategy.segment || 'UNKNOWN').toUpperCase()
                      }
                    </span>
                    
                    {/* 3. Risk Level */}
                    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                      strategy.riskLevel === 'VERY_HIGH' ? 'bg-red-100 text-red-800' :
                      strategy.riskLevel === 'HIGH' ? 'bg-red-100 text-red-700' :
                      strategy.riskLevel === 'MID' ? 'bg-yellow-100 text-yellow-700' :
                      strategy.riskLevel === 'LOW' ? 'bg-green-100 text-green-700' :
                      strategy.riskLevel === 'VERY_LOW' ? 'bg-green-100 text-green-800' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {strategy.riskLevel.replace('_', ' ')}
                    </span>
                    
                    {/* 4. Holding Period */}
                    <span 
                      className="px-1.5 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700 cursor-help flex items-center gap-1"
                      title={`Holding Period: ${strategy.holdingPeriod || 'Unknown'}`}
                    >
                      {(strategy.holdingPeriod || '').includes('7-30') || (strategy.holdingPeriod || '').includes('short') ? 'SHORT' :
                       (strategy.holdingPeriod || '').includes('30-90') || (strategy.holdingPeriod || '').includes('mid') ? 'MID' :
                       (strategy.holdingPeriod || '').includes('90+') || (strategy.holdingPeriod || '').includes('long') ? 'LONG' :
                       'MID'}
                      <Info size={8} />
                    </span>
                  </div>
                </div>
                
              </div>
            </div>

            {/* Strategy Details - For Options, Futures, and Hybrid with Legs */}
            {strategy.legs && strategy.legs.length > 0 && (strategy.strategyType === 'Options' || strategy.strategyType === 'Futures' || strategy.strategyType === 'Hybrid') && (
              <div className="px-4 py-4 border-b border-gray-200">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Strategy Legs
                  </h3>
                  <div className="text-xs">
                    <span className="text-gray-600">{strategy.status === 'active' ? 'Total P&L: ' : 'Booked P&L: '}</span>
                    <span className={`font-semibold ${
                      currentPnL >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {currentPnL >= 0 ? '+' : ''}{formatCurrency(Math.abs(currentPnL))}
                    </span>
                  </div>
                </div>
                <div className="space-y-2">
                  {strategy.legs.map((leg, index) => (
                    <div key={index} className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                      <div className="flex items-center gap-2 mb-2">
                        <div 
                          className="w-6 h-6 rounded-md flex items-center justify-center"
                          style={{ background: getActionColor(leg.action) + '20' }}
                        >
                          {leg.action === 'buy' ? 
                            <TrendingUp size={12} color={getActionColor(leg.action)} /> :
                            <TrendingDown size={12} color={getActionColor(leg.action)} />
                          }
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-gray-900 text-sm">
                              {(leg.action || leg.type || 'BUY').toUpperCase()} {leg.symbol || strategy.symbol || 'INSTRUMENT'}
                            </span>
                            {/* Show Qty for Options, Futures, and Hybrid */}
                            {(strategy.strategyType === 'Options' || strategy.strategyType === 'Futures' || strategy.strategyType === 'Hybrid') && (
                              <span className="text-xs text-gray-500 bg-gray-200 px-1 py-0.5 rounded">
                                Qty: {leg.quantity || 1}
                              </span>
                            )}
                          </div>
                          {/* Show CMP for Options, Futures, and Hybrid legs */}
                          <div className="text-xs text-gray-600">
                            CMP: <span className={`font-medium ${
                              (leg.currentPrice || strategy.currentPrice) >= (leg.entryPrice || strategy.entryPrice) ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {formatCurrencyDetailed(leg.currentPrice || strategy.currentPrice)}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className={`grid gap-2 text-xs ${strategy.status === 'closed' && leg.exitPrice ? 'grid-cols-3' : 'grid-cols-2'}`}>
                        <div>
                          <span className="text-gray-600 text-xs">Entry Price:</span>
                          <div className="font-semibold text-gray-900 text-xs">{formatCurrencyDetailed(leg.entryPrice || strategy.entryPrice)}</div>
                        </div>
                        {strategy.status === 'closed' && leg.exitPrice && (
                          <div>
                            <span className="text-gray-600 text-xs">Exit Price:</span>
                            <div className="font-semibold text-gray-900 text-xs">
                              {formatCurrencyDetailed(leg.exitPrice)}
                            </div>
                          </div>
                        )}
                        <div>
                          <span className="text-gray-600 text-xs">Lot Size:</span>
                          <div className="font-semibold text-gray-900 text-xs">{leg.lotSize || strategy.contractSize || 'N/A'}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Trade Details - For Equity and Futures */}
            {(!strategy.legs || strategy.legs.length === 0) && (
              <div className="px-4 py-4 border-b border-gray-200">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Trade Details
                  </h3>
                  <div className="text-xs">
                    <span className="text-gray-600">{strategy.status === 'active' ? 'Total P&L: ' : 'Booked P&L: '}</span>
                    <span className={`font-semibold ${
                      currentPnL >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {currentPnL >= 0 ? '+' : ''}{formatCurrency(Math.abs(currentPnL))}
                    </span>
                  </div>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                  <div className="flex items-center gap-2 mb-2">
                    <div 
                      className="w-6 h-6 rounded-md flex items-center justify-center"
                      style={{ background: getSegmentColor(strategy.segment) + '20' }}
                    >
                      <TrendingUp size={12} color={getSegmentColor(strategy.segment)} />
                    </div>
                    <div>
                      <div className="font-semibold text-gray-900 text-sm">
                        {strategy.id.includes('eq_') ? 'BUY' : 
                         strategy.id.includes('ft_') ? `${strategy.action?.toUpperCase() || 'BUY'} FUT` : 
                         strategy.strategyType === 'Hybrid' ? 'HYBRID' :
                         'BUY OPT'} {strategy.symbol}
                      </div>
                      {/* Show current price below symbol for ALL segments */}
                      <div className="text-xs text-gray-600">
                        CMP: <span className={`font-medium ${
                          strategy.currentPrice >= strategy.entryPrice ? 'text-green-600' : 'text-red-600'
                        }`}>
                          {formatCurrencyDetailed(strategy.currentPrice)}
                        </span>
                      </div>
                    </div>
                  </div>
                    {/* For Equity: 1 or 2-column layout based on status (Futures now use legs format) */}
                    {strategy.segment === 'equity' ? (
                      <div className={`grid gap-2 text-xs ${strategy.status === 'closed' ? 'grid-cols-2' : 'grid-cols-1'}`}>
                        <div>
                          <span className="text-gray-600 text-xs">Entry Price:</span>
                          <div className="font-semibold text-gray-900 text-xs">{formatCurrencyDetailed(strategy.entryPrice)}</div>
                        </div>
                        {strategy.status === 'closed' && (
                          <div>
                            <span className="text-gray-600 text-xs">Exit Price:</span>
                            <div className="font-semibold text-gray-900 text-xs">
                              {formatCurrencyDetailed(strategy.exitPrice || strategy.currentPrice)}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : null}
                </div>
              </div>
            )}


            {/* Action Footer */}
            <div className="px-4 py-4 bg-gray-50 border-t border-gray-200 flex justify-between items-center">
              <div className="flex gap-2">
                <button 
                  onClick={() => setShowDetailsModal(strategy)}
                  className="flex items-center gap-1 px-3 py-2 text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <Info size={12} />
                  <span className="text-xs font-medium">Details</span>
                </button>
                {strategy.status === 'active' && (
                  <ShareTradeButton trade={strategy} generateTradeUrl={generateTradeUrl} />
                )}
              </div>
              
              {strategy.status === 'active' && (
                <button
                  onClick={() => setShowAddToPortfolioModal(strategy)}
                  className={`flex items-center gap-1 px-4 py-2 rounded-lg font-semibold text-xs transition-all ${
                    isSelected
                      ? 'bg-gradient-to-r from-primary-500 to-primary-600 text-white shadow-lg'
                      : 'bg-gradient-to-r from-gray-600 to-gray-700 text-white hover:from-gray-700 hover:to-gray-800 shadow-md'
                  }`}
                >
                  <Plus size={14} />
                  Add to Portfolio
                </button>
              )}
            </div>
          </div>
        );
        } catch (error) {
          console.error('Error rendering strategy:', strategy, error);
          return (
            <div key={strategy.id} className="bg-red-50 border border-red-200 rounded-lg p-4">
              <p className="text-red-600">Error loading strategy: {strategy.strategy || 'Unknown'}</p>
            </div>
          );
        }
      })}
      
      {/* Details Modal */}
      {showDetailsModal && (
        <div className="fixed inset-0 bg-gray-500 bg-opacity-75 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden">
            {/* Modal Header */}
            <div className="px-4 py-3 border-b border-gray-200 bg-white flex justify-between items-center">
              <h3 className="text-base font-semibold text-gray-900">{showDetailsModal.strategy} - Details</h3>
              <button
                onClick={() => setShowDetailsModal(null)}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X size={18} className="text-gray-600" />
              </button>
            </div>
            
            {/* Modal Content - Capital & Risk | Targets & Stop Loss */}
            <div className="p-4 overflow-y-auto">
              {/* Capital & Risk Section */}
              <div className="mb-4">
                <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2 flex items-center gap-2">
                  <DollarSign size={14} />
                  Capital & Risk
                </h4>
                
                {/* Capital Required - Highlighted */}
                <div className="mb-3 p-3 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs text-gray-600 mb-1">Capital Required</div>
                      <div className="text-lg font-bold text-gray-900">
                        {showDetailsModal.id.includes('eq_') ? 'Flexible' : formatCurrency(Math.abs(showDetailsModal.capitalRequired))}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-gray-500">Risk Level</div>
                      <div className="text-sm font-bold" style={{ color: getRiskColor(showDetailsModal.riskLevel) }}>
                        {showDetailsModal.riskLevel}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Risk Metrics */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2 bg-blue-50 rounded-lg border border-blue-200 text-center">
                    <div className="text-xs text-gray-600 mb-1">Confidence</div>
                    <div className="text-sm font-bold text-blue-600">
                      {showDetailsModal.confidence || 85}%
                    </div>
                  </div>
                  <div className="p-2 bg-gray-50 rounded-lg border border-gray-200 text-center">
                    <div className="text-xs text-gray-600 mb-1">Risk:Reward</div>
                    <div className="text-sm font-bold text-gray-900">
                      {showDetailsModal.riskReward || '1:2'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Conditional Section - Targets/Stop Loss for Equity/Futures OR Max Profit/Loss for Options */}
              <div>
                {(showDetailsModal.segment === 'equity' || (showDetailsModal.segment === 'fno' && showDetailsModal.strategyType === 'Futures')) ? (
                  // Equity & Futures: Show Targets & Stop Loss
                  <>
                    <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2 flex items-center gap-2">
                      <Target size={14} />
                      Targets & Stop Loss
                    </h4>
                    
                    <div className="grid grid-cols-2 gap-2">
                      {/* Target Price */}
                      <div 
                        className="p-3 rounded-lg border"
                        style={{ 
                          background: 'linear-gradient(135deg, #10b98110 0%, #10b98105 100%)',
                          borderColor: '#10b98120'
                        }}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <Target size={12} color="#10b981" />
                          <span className="text-xs font-semibold text-gray-900">Target</span>
                        </div>
                        <div className="text-sm font-bold text-gray-900 mb-1">
                          {formatCurrencyDetailed(showDetailsModal.targetPrice)}
                        </div>
                        <div className="text-xs font-bold text-green-600">
                          +{formatCurrency((showDetailsModal.targetPrice - showDetailsModal.entryPrice) * 50)}
                        </div>
                      </div>

                      {/* Stop Loss */}
                      <div 
                        className="p-3 rounded-lg border"
                        style={{ 
                          background: 'linear-gradient(135deg, #ef444410 0%, #ef444405 100%)',
                          borderColor: '#ef444420'
                        }}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <Shield size={12} color="#ef4444" />
                          <span className="text-xs font-semibold text-gray-900">Stop Loss</span>
                        </div>
                        <div className="text-sm font-bold text-gray-900 mb-1">
                          {formatCurrencyDetailed(showDetailsModal.stopLoss)}
                        </div>
                        <div className="text-xs font-bold text-red-600">
                          -{formatCurrency(showDetailsModal.capitalRequired * 0.3)}
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  // Options: Show Max Profit & Max Loss
                  <>
                    <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2 flex items-center gap-2">
                      <TrendingUp size={14} />
                      Max Profit & Loss
                    </h4>
                    
                    <div className="grid grid-cols-2 gap-2">
                      <div className="p-3 rounded-lg border bg-gradient-to-br from-green-50 to-emerald-50 border-green-200">
                        <div className="flex items-center gap-2 mb-1">
                          <TrendingUp size={12} color="#10b981" />
                          <span className="text-xs font-semibold text-gray-900">Max Profit</span>
                        </div>
                        <div className="text-sm font-bold text-green-600">
                          +{formatCurrency(showDetailsModal.maxProfit || showDetailsModal.expectedReturn * 1000)}
                        </div>
                      </div>
                      
                      <div className="p-3 rounded-lg border bg-gradient-to-br from-red-50 to-rose-50 border-red-200">
                        <div className="flex items-center gap-2 mb-1">
                          <TrendingDown size={12} color="#ef4444" />
                          <span className="text-xs font-semibold text-gray-900">Max Loss</span>
                        </div>
                        <div className="text-sm font-bold text-red-600">
                          -{formatCurrency(showDetailsModal.maxLoss || showDetailsModal.capitalRequired * 0.5)}
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </div>
              
            </div>
          </div>
        </div>
      )}

      {/* Add to Portfolio Modal */}
      <AddToPortfolioModal
        strategy={showAddToPortfolioModal}
        isOpen={!!showAddToPortfolioModal}
        onClose={() => setShowAddToPortfolioModal(null)}
        onAddToPortfolio={(portfolioItem) => {
          console.log('Adding to portfolio:', portfolioItem);
          onAddToPortfolio(portfolioItem);
          setShowAddToPortfolioModal(null);
        }}
      />
    </div>
  );
};

export default StrategyCards;