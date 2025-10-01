import React from 'react';
import { useTrade } from '../../hooks/useTrade';
import StrategyFilters from './components/StrategyFilters';
import StrategyCards from './components/StrategyCards';
import StrategyDetails from './components/StrategyDetails';

const Trades = () => {
  const {
    segments,
    strategies,
    selectedSegment,
    selectedStrategy,
    loading,
    error,
    tradeStatus,
    activeFilters,
    showPopup,
    handleSegmentChange,
    handleStrategySelect,
    filterStrategiesByStatus,
    updateFilters,
    generateTradeUrl,
  } = useTrade();

  if (loading && !strategies.length) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center pb-20">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading trade advisory...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header with Trade Segments */}
      <div className="bg-gradient-to-r from-slate-50 to-gray-50 border-b border-gray-200 px-6 py-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-8">
              <div>
                <h1 className="text-lg font-medium text-gray-600 mb-2">Trade Segments</h1>
                <div className="flex gap-2">
                  {segments.map((segment) => (
                    <button
                      key={segment.id}
                      onClick={() => handleSegmentChange(segment)}
                      className={`relative px-8 py-3 rounded-full font-medium text-sm transition-all duration-300 ${
                        selectedSegment === segment.id
                          ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-200 transform scale-105'
                          : 'bg-white text-gray-600 hover:text-blue-600 hover:shadow-md border border-gray-200 hover:border-blue-200'
                      }`}
                    >
                      {segment.id === 'fno' ? 'F&O' : segment.name}
                      {selectedSegment === segment.id && (
                        <div className="absolute inset-0 bg-gradient-to-r from-blue-400 to-blue-500 rounded-full opacity-20 animate-pulse"></div>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Strategy Filters - Between header and content */}
      {selectedSegment && (
        <StrategyFilters
          selectedSegment={selectedSegment}
          activeFilters={activeFilters}
          onFilterChange={updateFilters}
          onToggleChange={filterStrategiesByStatus}
          activeStatus={tradeStatus}
        />
      )}

      {/* Error Display */}
      {error && (
        <div className="max-w-7xl mx-auto px-6 mt-6">
          <div className="p-4 bg-red-50 border border-red-200 rounded-xl">
            <div className="flex">
              <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="ml-3">
                <p className="text-sm text-red-800">{error}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-6 pt-6 space-y-6">
        {/* Strategy Cards */}
        <StrategyCards
          strategies={strategies}
          selectedStrategy={selectedStrategy}
          onStrategySelect={handleStrategySelect}
          onAddToPortfolio={(portfolioItem) => {
            console.log('Adding strategy to portfolio:', portfolioItem);
            console.log('Portfolio item keys:', Object.keys(portfolioItem));
            
            // Save to localStorage
            const existingPortfolio = JSON.parse(localStorage.getItem('userPortfolio') || '[]');
            console.log('Existing portfolio before:', existingPortfolio);
            
            const updatedPortfolio = [...existingPortfolio, portfolioItem];
            console.log('Updated portfolio after:', updatedPortfolio);
            
            localStorage.setItem('userPortfolio', JSON.stringify(updatedPortfolio));
            
            // Verify what was saved
            const savedPortfolio = JSON.parse(localStorage.getItem('userPortfolio') || '[]');
            console.log('Verified saved portfolio:', savedPortfolio);
            
            // Trigger a custom event to notify other components
            window.dispatchEvent(new CustomEvent('portfolioUpdated', { 
              detail: { portfolio: updatedPortfolio } 
            }));
            
            // Show success message (you can replace with toast notification)
            alert(`Added ${portfolioItem.quantity} ${portfolioItem.segment === 'equity' ? 'shares' : 'lots'} of ${portfolioItem.symbol} to portfolio!`);
          }}
          generateTradeUrl={generateTradeUrl}
        />

        {/* Strategy Details */}
        {showPopup && selectedStrategy && (
          <StrategyDetails
            strategy={selectedStrategy}
            onClose={() => handleStrategySelect(null)}
          />
        )}
      </div>
    </div>
  );
};

export default Trades;
