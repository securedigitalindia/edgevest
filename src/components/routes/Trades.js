import React from 'react';
import { useTrade } from '../../hooks/useTrade';
import SegmentSelector from './components/SegmentSelector';
import StrategyCards from './components/StrategyCards';
import StrategyDetails from './components/StrategyDetails';

const Trades = () => {
  const {
    segments,
    strategies,
    selectedSegment,
    selectedStrategy,
    livePrices,
    loading,
    error,
    handleSegmentChange,
    handleStrategySelect,
    refreshData,
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
      {/* Header */}
      <div className="bg-white shadow-sm border-b border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Trade Advisory</h1>
            <p className="text-sm text-gray-600">Smart trading strategies across all segments</p>
          </div>
          <button
            onClick={refreshData}
            className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="mx-4 mt-4 p-4 bg-danger-50 border border-danger-200 rounded-lg">
          <div className="flex">
            <svg className="w-5 h-5 text-danger-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="ml-3">
              <p className="text-sm text-danger-800">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Segment Selector */}
      <div className="px-4 pb-4">
        <SegmentSelector
          segments={segments}
          selectedSegment={selectedSegment}
          onSegmentChange={handleSegmentChange}
        />
      </div>

      {/* Main Content */}
      <div className="px-4 space-y-6">
        {/* Strategy Cards */}
        <StrategyCards
          strategies={strategies}
          selectedStrategy={selectedStrategy}
          onStrategySelect={handleStrategySelect}
          livePrices={livePrices}
          loading={loading}
        />

        {/* Strategy Details */}
        {selectedStrategy && (
          <StrategyDetails
            strategy={selectedStrategy}
            livePrice={livePrices[selectedStrategy.symbol]}
          />
        )}
      </div>
    </div>
  );
};

export default Trades;
