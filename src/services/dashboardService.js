import config from '../config/environment';
import {
  mockPortfolioData,
  mockActiveTrades,
  mockMarketData,
  mockRiskMetrics,
  mockTradeSuggestions,
} from '../mock/data/dashboardData';

class DashboardService {
  constructor() {
    this.baseUrl = config.apiUrl;
    this.useMock = config.useMock;
  }

  // Portfolio data
  async getPortfolioData() {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => resolve(mockPortfolioData), 500);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/portfolio`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching portfolio data:', error);
      throw error;
    }
  }

  // Active trades
  async getActiveTrades() {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => resolve(mockActiveTrades), 300);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/trades/active`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching active trades:', error);
      throw error;
    }
  }

  // Market data
  async getMarketData() {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => resolve(mockMarketData), 400);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/market`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching market data:', error);
      throw error;
    }
  }

  // Risk metrics
  async getRiskMetrics() {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => resolve(mockRiskMetrics), 350);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/risk-metrics`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching risk metrics:', error);
      throw error;
    }
  }

  // Trade suggestions
  async getTradeSuggestions() {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => resolve(mockTradeSuggestions), 600);
      });
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/trade-suggestions`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching trade suggestions:', error);
      throw error;
    }
  }

  // Dashboard overview (combined data)
  async getDashboardOverview() {
    try {
      console.log('DashboardService: Getting overview, useMock:', this.useMock);
      const [portfolio, trades, market, risk] = await Promise.all([
        this.getPortfolioData(),
        this.getActiveTrades(),
        this.getMarketData(),
        this.getRiskMetrics(),
      ]);

      const result = {
        portfolio,
        activeTrades: trades,
        marketData: market,
        riskMetrics: risk,
      };
      
      console.log('DashboardService: Returning overview data:', result);
      return result;
    } catch (error) {
      console.error('Error fetching dashboard overview:', error);
      throw error;
    }
  }

  // Execute trade
  async executeTrade(tradeData) {
    if (this.useMock) {
      return new Promise((resolve) => {
        setTimeout(() => {
          resolve({
            success: true,
            tradeId: `trade_${Date.now()}`,
            message: 'Trade executed successfully',
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
}

const dashboardService = new DashboardService();
export default dashboardService;
