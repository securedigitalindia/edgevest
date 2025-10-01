import React, { useState, useEffect } from 'react';
import { TrendingDown, Plus, Eye, EyeOff, Wallet, Activity, BarChart3, Info, Calendar } from 'lucide-react';

const Portfolio = () => {
  const [portfolio, setPortfolio] = useState(null);
  const [totalCapital, setTotalCapital] = useState(null);
  const [showAddCapitalModal, setShowAddCapitalModal] = useState(false);
  const [showCapital, setShowCapital] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard');

  // Load portfolio and capital from localStorage
  useEffect(() => {
    const loadPortfolio = () => {
      try {
        const savedPortfolio = localStorage.getItem('userPortfolio');
        if (savedPortfolio) {
          const portfolioData = JSON.parse(savedPortfolio);
          setPortfolio(portfolioData);
        } else {
          setPortfolio([]);
        }
      } catch (error) {
        setPortfolio([]);
      }
    };

    const loadCapital = () => {
      const savedCapital = localStorage.getItem('totalCapital');
      if (savedCapital) {
        setTotalCapital(parseFloat(savedCapital));
      } else {
        setTotalCapital(1000000);
      }
    };

    loadPortfolio();
    loadCapital();

    // Listen for portfolio updates
    const handlePortfolioUpdate = () => {
      loadPortfolio();
    };

    window.addEventListener('portfolioUpdated', handlePortfolioUpdate);
    return () => window.removeEventListener('portfolioUpdated', handlePortfolioUpdate);
  }, []);

  // Save capital changes
  useEffect(() => {
    if (totalCapital !== null) {
      localStorage.setItem('totalCapital', totalCapital.toString());
    }
  }, [totalCapital]);

  // Helper functions
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatPercentage = (value) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  const getOpenPositions = () => {
    if (!portfolio || !Array.isArray(portfolio)) return [];
    return portfolio.filter(position => position.status === 'active' || !position.status);
  };

  const getClosedPositions = () => {
    if (!portfolio || !Array.isArray(portfolio)) return [];
    return portfolio.filter(position => position.status === 'closed');
  };

  const getTotalAllocatedCapital = () => {
    if (!portfolio || !Array.isArray(portfolio)) return 0;
    return getOpenPositions().reduce((total, position) => {
      return total + (position.totalCapitalRequired || 0);
    }, 0);
  };

  const getTotalBookedPnL = () => {
    if (!portfolio || !Array.isArray(portfolio)) return 0;
    return getClosedPositions().reduce((total, position) => {
      return total + calculatePnL(position);
    }, 0);
  };

  const getTotalActivePnL = () => {
    if (!portfolio || !Array.isArray(portfolio)) return 0;
    return getOpenPositions().reduce((total, position) => {
      return total + calculateActivePnL(position);
    }, 0);
  };

  const getAdjustedCapital = () => {
    if (!totalCapital) return 0;
    return totalCapital + getTotalBookedPnL();
  };

  const getAvailableCapital = () => {
    if (!totalCapital) return 0;
    return getAdjustedCapital() - getTotalAllocatedCapital();
  };

  const getOverallROI = () => {
    if (!totalCapital || totalCapital === 0) return 0;
    const totalPnL = getTotalBookedPnL() + getTotalActivePnL();
    return (totalPnL / totalCapital) * 100;
  };

  const calculatePnL = (position) => {
    if (position.segment === 'equity') {
      const currentPrice = position.currentPrice || position.entryPrice;
      const pnl = (currentPrice - position.entryPrice) * position.quantity;
      return position.status === 'closed' ? pnl : 0;
    } else if (position.segment === 'fno' && position.legs) {
      return position.legs.reduce((total, leg) => {
        const currentPrice = leg.currentPrice || leg.entryPrice;
        const pnl = (currentPrice - leg.entryPrice) * leg.lotSize * leg.quantity;
        return total + (position.status === 'closed' ? pnl : 0);
      }, 0);
    }
    return 0;
  };

  const calculateActivePnL = (position) => {
    if (position.segment === 'equity') {
      const currentPrice = position.currentPrice || position.entryPrice;
      return (currentPrice - position.entryPrice) * position.quantity;
    } else if (position.segment === 'fno' && position.legs) {
      return position.legs.reduce((total, leg) => {
        const currentPrice = leg.currentPrice || leg.entryPrice;
        return total + (currentPrice - leg.entryPrice) * leg.lotSize * leg.quantity;
      }, 0);
    }
    return 0;
  };

  const closePosition = (positionId) => {
    if (!portfolio) return;
    const updatedPortfolio = portfolio.map(position => {
      if (position.id === positionId) {
        return {
          ...position,
          status: 'closed',
          closedAt: new Date().toISOString()
        };
      }
      return position;
    });
    setPortfolio(updatedPortfolio);
    localStorage.setItem('userPortfolio', JSON.stringify(updatedPortfolio));
    window.dispatchEvent(new CustomEvent('portfolioUpdated'));
  };

  const addCapital = (amount) => {
    if (!totalCapital) return;
    const newTotal = totalCapital + amount;
    setTotalCapital(newTotal);
    setShowAddCapitalModal(false);
  };

  // Position Card Component
  const PositionCard = ({ position, showActions = true }) => {
    const isActive = position.status === 'active' || !position.status;
    const pnl = isActive ? calculateActivePnL(position) : calculatePnL(position);
    const currentPrice = position.currentPrice || position.entryPrice;
    const exitPrice = position.exitPrice || currentPrice;

    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-3">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${position.segment === 'equity' ? 'bg-blue-500' : 'bg-green-500'}`}></div>
            <div>
              <h3 className="text-base font-semibold text-gray-900">{position.symbol}</h3>
              <p className="text-xs text-gray-600">{position.strategy}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
              isActive ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'
            }`}>
              {isActive ? 'ACTIVE' : 'CLOSED'}
            </span>
            {showActions && isActive && (
              <button
                onClick={() => closePosition(position.id)}
                className="px-2 py-1 bg-red-100 text-red-700 rounded-full text-xs font-medium hover:bg-red-200 transition-colors"
              >
                Close
              </button>
            )}
          </div>
        </div>

        {/* Basic Info */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">Type</div>
            <div className="font-semibold text-gray-900 text-sm">{position.segment.toUpperCase()}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">Quantity</div>
            <div className="font-semibold text-gray-900 text-sm">
              {position.quantity} {position.segment === 'equity' ? 'shares' : 'lots'}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">Entry Price</div>
            <div className="font-semibold text-gray-900 text-sm">
              {showCapital ? formatCurrency(position.entryPrice) : '••••'}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">
              {isActive ? 'Current Price' : 'Exit Price'}
            </div>
            <div className="font-semibold text-gray-900 text-sm">
              {showCapital ? formatCurrency(isActive ? currentPrice : exitPrice) : '••••'}
            </div>
          </div>
        </div>

        {/* P&L */}
        <div className="bg-gray-50 rounded-lg p-3 mb-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs text-gray-600">P&L</div>
              <div className={`text-lg font-bold ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {showCapital ? formatCurrency(pnl) : '••••••••'}
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs text-gray-600">Return</div>
              <div className={`text-sm font-semibold ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {position.entryPrice ? formatPercentage(((isActive ? currentPrice : exitPrice) - position.entryPrice) / position.entryPrice * 100) : '0%'}
              </div>
            </div>
          </div>
        </div>

        {/* F&O Legs Details */}
        {position.segment === 'fno' && position.legs && position.legs.length > 0 && (
          <div className="border-t border-gray-200 pt-3">
            <h4 className="text-xs font-semibold text-gray-900 mb-2 flex items-center gap-1">
              <Info size={12} />
              Legs Details
            </h4>
            <div className="space-y-2">
              {position.legs.map((leg, index) => (
                <div key={index} className="bg-blue-50 rounded-lg p-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-blue-900">Leg {index + 1}</span>
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      leg.action === 'buy' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                    }`}>
                      {leg.action.toUpperCase()}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <div className="text-gray-600">Instrument</div>
                      <div className="font-medium text-gray-900">{leg.instrument || 'N/A'}</div>
                    </div>
                    <div>
                      <div className="text-gray-600">Lot Size</div>
                      <div className="font-medium text-gray-900">{leg.lotSize || 'N/A'}</div>
                    </div>
                    <div>
                      <div className="text-gray-600">Entry Price</div>
                      <div className="font-medium text-gray-900">
                        {showCapital ? formatCurrency(leg.entryPrice || position.entryPrice) : '••••'}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-600">
                        {isActive ? 'Current' : 'Exit'} Price
                      </div>
                      <div className="font-medium text-gray-900">
                        {showCapital ? formatCurrency(isActive ? (leg.currentPrice || leg.entryPrice) : (leg.exitPrice || leg.currentPrice || leg.entryPrice)) : '••••'}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Additional Info */}
        <div className="border-t border-gray-200 pt-2">
          <div className="flex items-center gap-4 text-xs text-gray-600">
            <div className="flex items-center gap-1">
              <Calendar size={10} />
              <span>Added: {new Date(position.addedAt || Date.now()).toLocaleDateString()}</span>
            </div>
            {!isActive && position.closedAt && (
              <div className="flex items-center gap-1">
                <Calendar size={10} />
                <span>Closed: {new Date(position.closedAt).toLocaleDateString()}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  // Loading state
  if (portfolio === null || totalCapital === null) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading Portfolio...</p>
        </div>
      </div>
    );
  }

  const openPositions = getOpenPositions();
  const closedPositions = getClosedPositions();
  const totalBookedPnL = getTotalBookedPnL();
  const totalActivePnL = getTotalActivePnL();
  const overallROI = getOverallROI();

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Mobile Header */}
      <div className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-10">
        <div className="px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-bold text-gray-900">Portfolio</h1>
              <p className="text-xs text-gray-600">Dummy Trading Dashboard</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowCapital(!showCapital)}
                className="p-2 text-gray-600 hover:text-gray-900 transition-colors"
              >
                {showCapital ? <Eye size={16} /> : <EyeOff size={16} />}
              </button>
              <button
                onClick={() => setShowAddCapitalModal(true)}
                className="flex items-center gap-1 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
              >
                <Plus size={14} />
                Add Capital
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Tabs */}
      <div className="bg-white border-b border-gray-200 sticky top-16 z-10">
        <div className="flex">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`flex-1 flex flex-col items-center py-3 px-2 font-medium text-xs transition-all duration-200 ${
              activeTab === 'dashboard'
                ? 'bg-blue-50 text-blue-600 border-b-2 border-blue-500'
                : 'text-gray-600 hover:text-blue-600'
            }`}
          >
            <BarChart3 size={16} className="mb-1" />
            <span>Dashboard</span>
          </button>
          
          <button
            onClick={() => setActiveTab('open')}
            className={`flex-1 flex flex-col items-center py-3 px-2 font-medium text-xs transition-all duration-200 ${
              activeTab === 'open'
                ? 'bg-green-50 text-green-600 border-b-2 border-green-500'
                : 'text-gray-600 hover:text-green-600'
            }`}
          >
            <Activity size={16} className="mb-1" />
            <span>Open ({openPositions.length})</span>
          </button>
          
          <button
            onClick={() => setActiveTab('closed')}
            className={`flex-1 flex flex-col items-center py-3 px-2 font-medium text-xs transition-all duration-200 ${
              activeTab === 'closed'
                ? 'bg-gray-50 text-gray-600 border-b-2 border-gray-500'
                : 'text-gray-600 hover:text-gray-700'
            }`}
          >
            <TrendingDown size={16} className="mb-1" />
            <span>Closed ({closedPositions.length})</span>
          </button>
        </div>
      </div>

      <div className="px-4 py-4">
        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <div className="space-y-4">
            {/* Capital Overview Card */}
            <div className="bg-gradient-to-br from-blue-50 to-indigo-100 rounded-xl shadow-sm border border-blue-200 p-4">
              <div className="flex items-center gap-2 mb-4">
                <div className="p-2 bg-blue-600 rounded-lg">
                  <Wallet className="h-5 w-5 text-white" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-blue-900">Capital Overview</h3>
                  <p className="text-xs text-blue-600">Portfolio financial summary</p>
                </div>
              </div>
              
              <div className="space-y-3">
                {/* Total Capital */}
                <div className="bg-white/70 backdrop-blur-sm rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                    <span className="text-xs font-medium text-gray-700">Total Capital</span>
                  </div>
                  <div className="text-lg font-bold text-gray-900">
                    {showCapital ? formatCurrency(getAdjustedCapital()) : '••••••••'}
                  </div>
                  {showCapital && (
                    <div className="text-xs text-gray-600 mt-1">
                      Base: {formatCurrency(totalCapital)}
                      {totalBookedPnL !== 0 && (
                        <span className="ml-2">
                          ({totalBookedPnL >= 0 ? '+' : ''}{formatCurrency(totalBookedPnL)})
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Utilized Capital */}
                <div className="bg-white/70 backdrop-blur-sm rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="w-2 h-2 bg-orange-500 rounded-full"></div>
                    <span className="text-xs font-medium text-gray-700">Utilized Capital</span>
                  </div>
                  <div className="text-lg font-bold text-gray-900">
                    {showCapital ? formatCurrency(getTotalAllocatedCapital()) : '••••••••'}
                  </div>
                  {showCapital && (
                    <div className="text-xs text-gray-600 mt-1">
                      {Math.round((getTotalAllocatedCapital() / getAdjustedCapital()) * 100)}% of total
                    </div>
                  )}
                </div>

                {/* Booked P&L */}
                <div className="bg-white/70 backdrop-blur-sm rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <div className={`w-2 h-2 rounded-full ${totalBookedPnL >= 0 ? 'bg-green-500' : 'bg-red-500'}`}></div>
                    <span className="text-xs font-medium text-gray-700">Booked P&L</span>
                  </div>
                  <div className={`text-lg font-bold ${totalBookedPnL >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {showCapital ? formatCurrency(totalBookedPnL) : '••••••••'}
                  </div>
                  {showCapital && (
                    <div className={`text-xs mt-1 ${totalBookedPnL >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      From {closedPositions.length} closed trades
                    </div>
                  )}
                </div>

                {/* Running ROI */}
                <div className="bg-white/70 backdrop-blur-sm rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <div className={`w-2 h-2 rounded-full ${overallROI >= 0 ? 'bg-purple-500' : 'bg-orange-500'}`}></div>
                    <span className="text-xs font-medium text-gray-700">Running ROI</span>
                  </div>
                  <div className={`text-lg font-bold ${overallROI >= 0 ? 'text-purple-600' : 'text-orange-600'}`}>
                    {showCapital ? formatPercentage(overallROI) : '••••'}
                  </div>
                  {showCapital && (
                    <div className={`text-xs mt-1 ${overallROI >= 0 ? 'text-purple-600' : 'text-orange-600'}`}>
                      {formatCurrency(totalActivePnL)} unrealized
                    </div>
                  )}
                </div>
              </div>

              {/* Capital Utilization Bar */}
              {showCapital && (
                <div className="mt-4 bg-white/50 backdrop-blur-sm rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-gray-700">Capital Utilization</span>
                    <span className="text-xs text-gray-600">
                      {formatCurrency(getAvailableCapital())} available
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-gradient-to-r from-blue-500 to-orange-500 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${(getTotalAllocatedCapital() / getAdjustedCapital()) * 100}%` }}
                    ></div>
                  </div>
                  <div className="flex justify-between text-xs text-gray-600 mt-1">
                    <span>0%</span>
                    <span>{Math.round((getTotalAllocatedCapital() / getAdjustedCapital()) * 100)}% utilized</span>
                    <span>100%</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Open Positions Tab */}
        {activeTab === 'open' && (
          <div className="space-y-4">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Open Positions</h3>
                  <p className="text-xs text-gray-600">Active trades with real-time P&L</p>
                </div>
                <div className="text-right">
                  <div className="text-xs text-gray-600">Total P&L</div>
                  <div className={`text-lg font-bold ${totalActivePnL >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {showCapital ? formatCurrency(totalActivePnL) : '••••••••'}
                  </div>
                </div>
              </div>
            </div>

            {/* Positions */}
            {openPositions.length > 0 ? (
              <div>
                {openPositions.map((position) => (
                  <PositionCard key={position.id} position={position} showActions={true} />
                ))}
              </div>
            ) : (
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
                <div className="text-center">
                  <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
                    <Activity className="h-6 w-6 text-gray-400" />
                  </div>
                  <p className="text-gray-600 text-sm">No open positions</p>
                  <p className="text-xs text-gray-500">Start trading to see positions here</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Closed Positions Tab */}
        {activeTab === 'closed' && (
          <div className="space-y-4">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Closed Positions</h3>
                  <p className="text-xs text-gray-600">Historical trades with realized P&L</p>
                </div>
                <div className="text-right">
                  <div className="text-xs text-gray-600">Total Booked P&L</div>
                  <div className={`text-lg font-bold ${totalBookedPnL >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {showCapital ? formatCurrency(totalBookedPnL) : '••••••••'}
                  </div>
                </div>
              </div>
            </div>

            {/* Positions */}
            {closedPositions.length > 0 ? (
              <div>
                {closedPositions.map((position) => (
                  <PositionCard key={position.id} position={position} showActions={false} />
                ))}
              </div>
            ) : (
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
                <div className="text-center">
                  <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
                    <TrendingDown className="h-6 w-6 text-gray-400" />
                  </div>
                  <p className="text-gray-600 text-sm">No closed positions</p>
                  <p className="text-xs text-gray-500">Close positions to see profit/loss here</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {(!portfolio || portfolio.length === 0) && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <Wallet className="h-8 w-8 text-blue-600" />
              </div>
              <h3 className="text-base font-semibold text-gray-900 mb-2">Start Your Dummy Trading Journey</h3>
              <p className="text-gray-600 mb-4 text-sm">
                Add trades from the Trades section to build your portfolio and track your dummy trading performance.
              </p>
              <button
                onClick={() => window.location.href = '/trades'}
                className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
              >
                <Plus size={14} />
                Browse Trades
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Add Capital Modal */}
      {showAddCapitalModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-end z-50">
          <div className="bg-white rounded-t-xl w-full max-h-96 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Add Capital</h3>
              <button
                onClick={() => setShowAddCapitalModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>
            <p className="text-sm text-gray-600 mb-6">
              Add more capital to your dummy trading account.
            </p>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => addCapital(100000)}
                  className="p-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <div className="font-semibold">+₹1,00,000</div>
                  <div className="text-xs text-gray-500">Quick Add</div>
                </button>
                <button
                  onClick={() => addCapital(500000)}
                  className="p-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <div className="font-semibold">+₹5,00,000</div>
                  <div className="text-xs text-gray-500">Quick Add</div>
                </button>
              </div>
              <button
                onClick={() => setShowAddCapitalModal(false)}
                className="w-full py-3 px-4 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Portfolio;