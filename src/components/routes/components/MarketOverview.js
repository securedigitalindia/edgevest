import React from 'react';

const MarketOverview = ({ marketData }) => {
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

  // Default market data to prevent errors
  const defaultMarketData = {
    indices: [],
    trendingStocks: [],
    marketStatus: 'closed',
  };

  const data = marketData || defaultMarketData;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Market Overview</h2>
        <div className={`px-3 py-1 rounded-full text-sm font-medium ${
          data.marketStatus === 'open' 
            ? 'bg-success-100 text-success-800' 
            : 'bg-gray-100 text-gray-800'
        }`}>
          {data.marketStatus === 'open' ? 'Market Open' : 'Market Closed'}
        </div>
      </div>

      {/* Indices */}
      <div className="mb-6">
        <h3 className="text-sm font-medium text-gray-600 mb-3">Key Indices</h3>
        <div className="space-y-3">
          {data.indices && data.indices.length > 0 ? data.indices.map((index) => (
            <div key={index.symbol} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
              <div>
                <p className="font-medium text-gray-900">{index.name}</p>
                <p className="text-sm text-gray-600">{index.symbol}</p>
              </div>
              <div className="text-right">
                <p className="font-semibold text-gray-900">{formatPrice(index.value)}</p>
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
          )) : (
            <div className="text-center py-4 text-gray-500">
              <p>No market data available</p>
            </div>
          )}
        </div>
      </div>

      {/* Trending Stocks */}
      <div>
        <h3 className="text-sm font-medium text-gray-600 mb-3">Trending Stocks</h3>
        <div className="space-y-2">
          {data.trendingStocks && data.trendingStocks.length > 0 ? data.trendingStocks.map((stock) => (
            <div key={stock.symbol} className="flex items-center justify-between p-3 hover:bg-gray-50 rounded-lg transition-colors">
              <div>
                <p className="font-medium text-gray-900">{stock.symbol}</p>
                <p className="text-sm text-gray-600">{stock.name}</p>
              </div>
              <div className="text-right">
                <p className="font-semibold text-gray-900">{formatPrice(stock.price)}</p>
                <div className="flex items-center space-x-2">
                  <span className={`text-sm font-medium ${
                    stock.change >= 0 ? 'text-success-600' : 'text-danger-600'
                  }`}>
                    {formatChange(stock.change)}
                  </span>
                  <span className={`text-sm ${
                    stock.changePercent >= 0 ? 'text-success-600' : 'text-danger-600'
                  }`}>
                    {formatPercentage(stock.changePercent)}
                  </span>
                </div>
                <p className="text-xs text-gray-500">Vol: {stock.volume}</p>
              </div>
            </div>
          )) : (
            <div className="text-center py-4 text-gray-500">
              <p>No trending stocks data available</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MarketOverview;