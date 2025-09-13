import React from 'react';

const RiskMetrics = ({ riskMetrics }) => {
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount || 0);
  };

  const getRiskColor = (risk) => {
    const numRisk = risk || 0;
    if (numRisk <= 5) return 'text-success-600 bg-success-100';
    if (numRisk <= 10) return 'text-warning-600 bg-warning-100';
    return 'text-danger-600 bg-danger-100';
  };

  const getRiskLabel = (risk) => {
    const numRisk = risk || 0;
    if (numRisk <= 5) return 'Low Risk';
    if (numRisk <= 10) return 'Medium Risk';
    return 'High Risk';
  };

  // Default risk metrics to prevent errors
  const defaultRiskMetrics = {
    portfolioRisk: 0,
    maxRisk: 15.0,
    riskUtilization: 0,
    var95: 0,
    maxDrawdown: 0,
    sharpeRatio: 0,
  };

  const data = riskMetrics || defaultRiskMetrics;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Risk Analysis</h2>
        <div className={`px-3 py-1 rounded-full text-sm font-medium ${getRiskColor(data.portfolioRisk)}`}>
          {getRiskLabel(data.portfolioRisk)}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="text-center p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-600 mb-1">Portfolio Risk</p>
          <p className="text-2xl font-bold text-gray-900">{data.portfolioRisk}%</p>
          <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
            <div
              className="bg-primary-600 h-2 rounded-full"
              style={{ width: `${data.maxRisk > 0 ? (data.portfolioRisk / data.maxRisk) * 100 : 0}%` }}
            ></div>
          </div>
        </div>
        <div className="text-center p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-600 mb-1">Max Drawdown</p>
          <p className="text-2xl font-bold text-gray-900">{data.maxDrawdown}%</p>
          <p className="text-xs text-gray-500 mt-1">Historical maximum</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="text-center">
          <p className="text-sm text-gray-600 mb-1">VaR (95%)</p>
          <p className="text-lg font-semibold text-gray-900">{formatCurrency(data.var95)}</p>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-600 mb-1">Sharpe Ratio</p>
          <p className="text-lg font-semibold text-gray-900">{data.sharpeRatio}</p>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-600 mb-1">Risk Utilization</p>
          <p className="text-lg font-semibold text-gray-900">{data.riskUtilization}%</p>
        </div>
      </div>

      {/* Risk Utilization Bar */}
      <div className="mt-4">
        <div className="flex justify-between text-sm text-gray-600 mb-2">
          <span>Risk Utilization vs Limit</span>
          <span>{data.riskUtilization}% / 100%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-300 ${
              data.riskUtilization > 80 ? 'bg-danger-500' : 
              data.riskUtilization > 60 ? 'bg-warning-500' : 'bg-success-500'
            }`}
            style={{ width: `${Math.min(data.riskUtilization, 100)}%` }}
          ></div>
        </div>
      </div>
    </div>
  );
};

export default RiskMetrics;
