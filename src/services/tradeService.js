import config from '../config/environment';
import { mockTradeStrategies, mockMarketData, tradingSegments } from '../mock/data/tradeData';

class TradeService {
  constructor() {
    this.baseUrl = config.apiUrl;
    this.useMock = config.useMock;
  }

  // Get all trading segments
  async getTradingSegments() {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => resolve(tradingSegments), 200);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/trading-segments`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching trading segments:', error);
      throw error;
    }
  }

  // Get strategies for a specific segment
  async getStrategiesBySegment(segment) {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => {
          const strategies = mockTradeStrategies[segment] || [];
          resolve(strategies);
        }, 300);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/strategies/${segment}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching strategies:', error);
      throw error;
    }
  }

  // Get market data for trading
  async getMarketData() {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => resolve(mockMarketData), 250);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/market-data`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching market data:', error);
      throw error;
    }
  }

  // Get strategy details by ID
  async getStrategyDetails(strategyId) {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => {
          // Find strategy across all segments
          let strategy = null;
          for (const segment in mockTradeStrategies) {
            const found = mockTradeStrategies[segment].find(s => s.id === strategyId);
            if (found) {
              strategy = found;
              break;
            }
          }
          resolve(strategy);
        }, 200);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/strategy/${strategyId}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching strategy details:', error);
      throw error;
    }
  }

  // Execute a trade
  async executeTrade(tradeData) {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => {
          resolve({
            success: true,
            tradeId: `trade_${Date.now()}`,
            orderId: `ORD_${Date.now()}`,
            message: 'Trade executed successfully',
            executionDetails: {
              executedPrice: tradeData.entryType === 'market' ? tradeData.entryPrice : tradeData.entryPrice,
              executionTime: new Date().toISOString(),
              status: 'executed',
            }
          });
        }, 1000);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/trades/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(tradeData),
      });
      return await response.json();
    } catch (error) {
      console.error('Error executing trade:', error);
      throw error;
    }
  }

  // Get live prices for a symbol
  async getLivePrice(symbol) {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => {
          // Mock live price with small variation
          const basePrice = this.getBasePrice(symbol);
          const variation = (Math.random() - 0.5) * 0.02; // ±1% variation
          const livePrice = basePrice * (1 + variation);
          resolve({
            symbol,
            price: livePrice,
            change: livePrice - basePrice,
            changePercent: variation * 100,
            timestamp: new Date().toISOString(),
          });
        }, 500);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/live-price/${symbol}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching live price:', error);
      throw error;
    }
  }

  // Helper method to get base price for mock data
  getBasePrice(symbol) {
    const basePrices = {
      'RELIANCE': 2520.75,
      'INFY': 1580.00,
      'NIFTY50': 22850.00,
      'BANKNIFTY': 48520.00,
      'GOLD': 62500.00,
      'CRUDE': 5200.00,
    };
    return basePrices[symbol] || 1000;
  }

  // Get risk analysis for a strategy
  async getRiskAnalysis(strategyId) {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => {
          resolve({
            strategyId,
            riskScore: Math.floor(Math.random() * 40) + 30, // 30-70 range
            maxLoss: Math.floor(Math.random() * 10000) + 5000,
            probabilityOfProfit: Math.floor(Math.random() * 30) + 60, // 60-90%
            var95: Math.floor(Math.random() * 5000) + 2000,
            sharpeRatio: (Math.random() * 2 + 0.5).toFixed(2),
            recommendations: [
              'Consider position sizing based on risk tolerance',
              'Monitor stop-loss levels closely',
              'Review strategy performance regularly'
            ]
          });
        }, 400);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/risk-analysis/${strategyId}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching risk analysis:', error);
      throw error;
    }
  }
}

const tradeService = new TradeService();
export default tradeService;
