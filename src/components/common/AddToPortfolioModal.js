import React, { useState, useEffect } from 'react';
import { X, Plus, Minus, DollarSign, AlertCircle } from 'lucide-react';

const AddToPortfolioModal = ({ strategy, isOpen, onClose, onAddToPortfolio }) => {
  const [quantity, setQuantity] = useState(1);
  const [capitalRequired, setCapitalRequired] = useState(0);
  const [maxQuantity, setMaxQuantity] = useState(1);
  const [suggestedQuantity, setSuggestedQuantity] = useState(1);
  const [availableCapital, setAvailableCapital] = useState(500000); // Default fallback

  const calculateAvailableCapital = () => {
    const savedTotalCapital = localStorage.getItem('totalCapital');
    const savedPortfolio = localStorage.getItem('userPortfolio');
    
    if (savedTotalCapital && savedPortfolio) {
      const totalCapital = parseFloat(savedTotalCapital);
      const portfolio = JSON.parse(savedPortfolio);
      
      // Get total booked P&L from closed positions
      const totalBookedPnL = portfolio
        .filter(position => position.status === 'closed')
        .reduce((total, position) => {
          // Calculate P&L for closed positions (same logic as Portfolio)
          if (position.segment === 'equity') {
            const currentPrice = position.currentPrice || position.entryPrice;
            const pnl = (currentPrice - position.entryPrice) * position.quantity;
            return total + pnl;
          } else if (position.segment === 'fno' && position.legs) {
            return total + position.legs.reduce((legTotal, leg) => {
              const currentPrice = leg.currentPrice || leg.entryPrice;
              const pnl = (currentPrice - leg.entryPrice) * leg.lotSize * leg.quantity;
              return legTotal + pnl;
            }, 0);
          }
          return total;
        }, 0);
      
      // Adjusted capital = total capital + booked P&L (same as Portfolio)
      const adjustedCapital = totalCapital + totalBookedPnL;
      
      // Only count allocated capital from open positions (same as Portfolio)
      const allocatedCapital = portfolio
        .filter(position => position.status === 'active' || !position.status)
        .reduce((total, position) => {
          return total + (position.totalCapitalRequired || 0);
        }, 0);
      
      const available = adjustedCapital - allocatedCapital;
      setAvailableCapital(available);
    }
  };

  useEffect(() => {
    calculateAvailableCapital();

    // Listen for portfolio updates to refresh available capital
    const handlePortfolioUpdate = () => {
      calculateAvailableCapital();
    };

    window.addEventListener('portfolioUpdated', handlePortfolioUpdate);
    return () => window.removeEventListener('portfolioUpdated', handlePortfolioUpdate);
  }, []);

  // Risk-based position sizing percentages
  const getRiskPercentage = (riskLevel) => {
    switch (riskLevel?.toUpperCase()) {
      case 'VERY_LOW':
        return 0.50; // 50%
      case 'LOW':
        return 0.25; // 25%
      case 'MID':
        return 0.15; // 15%
      case 'HIGH':
        return 0.10; // 10%
      case 'VERY_HIGH':
        return 0.05; // 5%
      default:
        return 0.15; // Default to 15% for unknown risk levels
    }
  };

  useEffect(() => {
    if (strategy) {
      // For equity, capital per share = CMP, for F&O = capitalRequired
      const capitalPerUnit = strategy.segment === 'equity' 
        ? (strategy.currentPrice || strategy.entryPrice || 1000) // Use CMP as fallback
        : strategy.capitalRequired;
      
      // Calculate maximum quantity based on available capital
      const maxQty = Math.floor(availableCapital / capitalPerUnit);
      setMaxQuantity(Math.max(1, maxQty));
      
      // Calculate suggested quantity based on risk level
      const riskPercentage = getRiskPercentage(strategy.riskLevel);
      const suggestedCapital = availableCapital * riskPercentage;
      const suggestedQty = Math.floor(suggestedCapital / capitalPerUnit);
      setSuggestedQuantity(Math.max(1, Math.min(suggestedQty, maxQty)));
      
      setQuantity(1);
      setCapitalRequired(capitalPerUnit);
    }
  }, [strategy, availableCapital]);

  const handleQuantityChange = (newQuantity) => {
    if (newQuantity >= 1 && newQuantity <= maxQuantity) {
      setQuantity(newQuantity);
      // For equity, capital per share = CMP, for F&O = capitalRequired
      const capitalPerUnit = strategy.segment === 'equity' 
        ? (strategy.currentPrice || strategy.entryPrice || 1000)
        : strategy.capitalRequired;
      setCapitalRequired(capitalPerUnit * newQuantity);
    }
  };

  const handleSuggestedQuantity = () => {
    setQuantity(suggestedQuantity);
    const capitalPerUnit = strategy.segment === 'equity' 
      ? (strategy.currentPrice || strategy.entryPrice || 1000)
      : strategy.capitalRequired;
    setCapitalRequired(capitalPerUnit * suggestedQuantity);
  };

  const handleAddToPortfolio = () => {
    // For equity, entry price = CMP, for F&O = use legs data
    let entryPrice;
    let legsData = [];
    
    if (strategy.segment === 'equity') {
      entryPrice = strategy.currentPrice || strategy.entryPrice || 1000;
    } else {
      // For F&O, preserve legs data and calculate proper entry price
      legsData = strategy.legs || [];
      // For F&O, entry price is the strategy's entry price (not CMP)
      entryPrice = strategy.entryPrice || strategy.currentPrice || 1000;
    }
    
    const portfolioItem = {
      // Essential portfolio fields
      id: strategy.id + '_' + Date.now(), // Ensure unique ID
      symbol: strategy.symbol,
      name: strategy.name,
      strategy: strategy.strategy,
      segment: strategy.segment,
      quantity: quantity,
      entryPrice: entryPrice,
      currentPrice: strategy.currentPrice || strategy.entryPrice || entryPrice,
      totalCapitalRequired: capitalRequired,
      legs: legsData, // Preserve F&O legs data
      status: 'active', // Set status as active by default
      addedAt: new Date().toISOString(),
      
      // Preserve some strategy metadata
      riskLevel: strategy.riskLevel,
      confidence: strategy.confidence,
      reasoning: strategy.reasoning
    };
    
    console.log('Creating portfolio item:', portfolioItem);
    onAddToPortfolio(portfolioItem);
    onClose();
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const getSegmentInfo = () => {
    if (strategy.segment === 'equity') {
      return {
        label: 'Shares',
        description: 'Number of shares to purchase',
        icon: '📈'
      };
    } else {
      return {
        label: 'Lots',
        description: 'Number of lots (multiplier)',
        icon: '🎯'
      };
    }
  };

  if (!isOpen || !strategy) return null;

  const segmentInfo = getSegmentInfo();

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50">
      {/* Bottom Sheet */}
      <div className="absolute bottom-0 left-0 right-0 bg-white max-h-[90vh] overflow-y-auto rounded-t-2xl">
        {/* Handle Bar */}
        <div className="flex justify-center pt-3 pb-2">
          <div className="w-12 h-1 bg-gray-300 rounded-full"></div>
        </div>

        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Add to Portfolio</h2>
            <p className="text-sm text-gray-600">{strategy.strategy} - {strategy.symbol}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Strategy Info */}
        <div className="px-6 py-4 bg-gray-50 border-b border-gray-200">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <span className="text-lg">{segmentInfo.icon}</span>
            </div>
            <div>
              <div className="font-semibold text-gray-900">
                {strategy.segment === 'equity' ? 'Equity Trade' : 'F&O Trade'}
              </div>
              <div className="text-sm text-gray-600">
                {strategy.strategyType || strategy.segment.toUpperCase()}
              </div>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-gray-600">
                {strategy.segment === 'equity' ? 'Current Price (CMP)' : 'Capital per Lot'}
              </div>
              <div className="font-semibold">
                {strategy.segment === 'equity' 
                  ? formatCurrency(strategy.currentPrice || strategy.entryPrice || 1000)
                  : formatCurrency(strategy.capitalRequired)
                }
              </div>
            </div>
            <div>
              <div className="text-gray-600">Risk Level</div>
              <div className={`font-semibold ${
                strategy.riskLevel === 'VERY_HIGH' ? 'text-red-800' :
                strategy.riskLevel === 'HIGH' ? 'text-red-600' :
                strategy.riskLevel === 'MID' ? 'text-yellow-600' :
                strategy.riskLevel === 'LOW' ? 'text-green-600' :
                strategy.riskLevel === 'VERY_LOW' ? 'text-green-800' : 'text-gray-600'
              }`}>
                {strategy.riskLevel.replace('_', ' ')}
              </div>
            </div>
          </div>
        </div>

        {/* Quantity Selection */}
        <div className="px-6 py-6">
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Select {segmentInfo.label}
            </h3>
            <p className="text-sm text-gray-600 mb-4">{segmentInfo.description}</p>

            {/* Quantity Selector */}
            <div className="flex items-center justify-between bg-gray-50 rounded-xl p-4">
              <button
                onClick={() => handleQuantityChange(quantity - 1)}
                disabled={quantity <= 1}
                className="w-10 h-10 bg-white rounded-lg border border-gray-300 flex items-center justify-center hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Minus size={16} />
              </button>

              <div className="text-center">
                <div className="text-3xl font-bold text-gray-900">{quantity}</div>
                <div className="text-sm text-gray-600">{segmentInfo.label}</div>
              </div>

              <button
                onClick={() => handleQuantityChange(quantity + 1)}
                disabled={quantity >= maxQuantity}
                className="w-10 h-10 bg-white rounded-lg border border-gray-300 flex items-center justify-center hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Plus size={16} />
              </button>
            </div>

            {/* Suggested Quantity - Always Show */}
            <div className="mt-4 text-center">
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-3">
                <div className="text-center">
                  <p className="text-yellow-800 font-bold text-lg">🎯 SUGGESTED QUANTITY</p>
                  <p className="text-yellow-900 font-bold text-2xl">
                    {suggestedQuantity} {segmentInfo.label.toUpperCase()}
                  </p>
                  <p className="text-yellow-700 text-sm">
                    {Math.round(getRiskPercentage(strategy.riskLevel) * 100)}% of available capital
                  </p>
                </div>
              </div>
              
              <button
                onClick={handleSuggestedQuantity}
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
              >
                Use Suggested: {suggestedQuantity} {segmentInfo.label.toLowerCase()}
              </button>
            </div>

            {/* Max Quantity Info */}
            <div className="mt-3 text-center">
              <span className="text-sm text-gray-500">
                Maximum: {maxQuantity} {segmentInfo.label.toLowerCase()} 
                (based on available capital: {formatCurrency(availableCapital)})
              </span>
            </div>
          </div>

          {/* Capital Calculation */}
          <div className="bg-blue-50 rounded-xl p-4 border border-blue-200">
            <div className="flex items-center gap-2 mb-2">
              <DollarSign size={16} className="text-blue-600" />
              <span className="font-semibold text-blue-900">Total Capital Required</span>
            </div>
            <div className="text-2xl font-bold text-blue-900">
              {formatCurrency(capitalRequired)}
            </div>
            <div className="text-sm text-blue-700 mt-1">
              {quantity} {segmentInfo.label.toLowerCase()} × {
                strategy.segment === 'equity' 
                  ? formatCurrency(strategy.currentPrice || strategy.entryPrice || 1000)
                  : formatCurrency(strategy.capitalRequired)
              }
            </div>
          </div>

          {/* Risk Warning */}
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertCircle size={16} className="text-yellow-600 mt-0.5" />
              <div className="text-sm text-yellow-800">
                <div className="font-medium mb-1">Risk Warning</div>
                <div>This is a {strategy.riskLevel.replace('_', ' ').toLowerCase()} risk trade. Please ensure you understand the risks involved before adding to your portfolio.</div>
              </div>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="px-6 py-4 border-t border-gray-200 space-y-3">
          <button
            onClick={handleAddToPortfolio}
            className="w-full py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-lg font-semibold hover:from-blue-700 hover:to-blue-800 transition-all shadow-md"
          >
            Add {quantity} {segmentInfo.label.toLowerCase()} to Portfolio
          </button>
          
          <button
            onClick={onClose}
            className="w-full py-3 border border-gray-300 text-gray-700 rounded-lg font-semibold hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default AddToPortfolioModal;
