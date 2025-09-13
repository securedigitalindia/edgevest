import React from 'react';
import { useDashboard } from '../../hooks/useDashboard';
import PortfolioSummary from './components/PortfolioSummary';
import ActiveTrades from './components/ActiveTrades';
import MarketOverview from './components/MarketOverview';
import RiskMetrics from './components/RiskMetrics';
import TradeSuggestions from './components/TradeSuggestions';
import QuickActions from './components/QuickActions';

const Dashboard = () => {
  const { 
    portfolio, 
    activeTrades, 
    marketData, 
    riskMetrics, 
    loading, 
    refreshing, 
    refreshData 
  } = useDashboard();

  if (loading && !refreshing) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading your smart investment dashboard...</p>
        </div>
      </div>
    );
  }

  console.log('Dashboard render - portfolio:', portfolio, 'loading:', loading, 'refreshing:', refreshing);

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-white shadow-sm border-b border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">EdgeVest</h1>
            <p className="text-sm text-gray-600">Smart Investment Dashboard</p>
          </div>
          <button
            onClick={refreshData}
            disabled={refreshing}
            className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg
              className={`w-5 h-5 ${refreshing ? 'animate-spin' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Dashboard Content */}
      <div className="px-4 py-6 space-y-6">
        {/* Portfolio Summary */}
        <PortfolioSummary portfolio={portfolio} />

        {/* Quick Actions */}
        <QuickActions />

        {/* Market Overview */}
        <MarketOverview marketData={marketData} />

        {/* Risk Metrics */}
        <RiskMetrics riskMetrics={riskMetrics} />

        {/* Active Trades */}
        <ActiveTrades trades={activeTrades} />

        {/* Trade Suggestions */}
        <TradeSuggestions />
      </div>
    </div>
  );
};

export default Dashboard;
