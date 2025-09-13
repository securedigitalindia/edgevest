import React from 'react';

const TradeMarketOverview = ({ marketData }) => {
  const formatPrice = (price) => {
    return new Intl.NumberFormat('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(price);
  };

  const formatChange = (change) => {
    return `${change >= 0 ? '+' : ''}${change.toFixed(2)}`;
  };

  const formatPercentage = (value) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  if (!marketData) return null;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Market Overview</h2>
        <div className={`px-3 py-1 rounded-full text-sm font-medium ${
          marketData.marketStatus === 'open' 
            ? 'bg-success-100 text-success-800' 
            : 'bg-gray-100 text-gray-800'
        }`}>
          {marketData.marketStatus === 'open' ? 'Market Open' : 'Market Closed'}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Indices */}
        <div>
          <h3 className="text-sm font-medium text-gray-600 mb-3">Key Indices</h3>
          <div className="space-y-2">
            {marketData.indices.map((index) => (
              <div key={index.symbol} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <p className="font-medium text-gray-900">{index.symbol}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-gray-900">{formatPrice(index.price)}</p>
                  <div className="flex items-center space-x-2">
                    <span className={`text-sm font-medium ${
                      index.change >= 0 ? 'text-success-600' : 'text-danger-600'
                    }`}>
                      {formatChange(index.change)}
                    </span>
                    <span className={`text-sm ${
                      index.changePercent >= 0 ? 'text-success-600' : 'text-danger-600'
                    }`}>
                      {formatPercentage(index.changePercent)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Commodities */}
        <div>
          <h3 className="text-sm font-medium text-gray-600 mb-3">Commodities</h3>
          <div className="space-y-2">
            {marketData.commodities.map((commodity) => (
              <div key={commodity.symbol} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <p className="font-medium text-gray-900">{commodity.symbol}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-gray-900">{formatPrice(commodity.price)}</p>
                  <div className="flex items-center space-x-2">
                    <span className={`text-sm font-medium ${
                      commodity.change >= 0 ? 'text-success-600' : 'text-danger-600'
                    }`}>
                      {formatChange(commodity.change)}
                    </span>
                    <span className={`text-sm ${
                      commodity.changePercent >= 0 ? 'text-success-600' : 'text-danger-600'
                    }`}>
                      {formatPercentage(commodity.changePercent)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* VIX */}
      <div className="mt-4 pt-4 border-t border-gray-200">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600">Volatility Index (VIX)</p>
          </div>
          <div className="text-right">
            <p className="text-lg font-semibold text-gray-900">{marketData.vix}</p>
            <p className="text-xs text-gray-500">
              {marketData.vix < 20 ? 'Low Volatility' : 
               marketData.vix < 30 ? 'Moderate Volatility' : 'High Volatility'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TradeMarketOverview;
