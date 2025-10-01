// Mock data for trade advisory
export const tradingSegments = [
  {
    id: 'equity',
    name: 'Equity',
    icon: '📈',
    description: 'Direct equity investments',
    color: 'bg-blue-100 text-blue-800',
  },
  {
    id: 'fno',
    name: 'F&O',
    icon: '🎯',
    description: 'Futures & Options trading',
    color: 'bg-purple-100 text-purple-800',
  },
];

export const mockTradeStrategies = {
  equity: [
    {
      id: 'eq_1',
      symbol: 'RELIANCE',
      name: 'Reliance Industries Ltd',
      strategy: 'Momentum Breakout',
      confidence: 85,
      riskLevel: 'MID',
      capitalRequired: 50000,
      expectedReturn: 12.5,
      riskReward: '1:2.5',
      maxProfit: 129250,
      maxLoss: 70725,
      holdingPeriod: '7-10 days',
      entryType: 'market',
      entryPrice: 2520.75,
      currentPrice: 2545.30,
      targetPrice: 2700.00,
      stopLoss: 2400.00,
      reasoning: 'Strong quarterly results, technical breakout above resistance level',
      technicalIndicators: ['RSI: 65', 'MACD: Bullish', 'Volume: High'],
      marketCap: 'Large Cap',
      sector: 'Oil & Gas',
      segment: 'equity',
      action: 'buy',
      status: 'active',
      targets: [
        { level: 2700, profit: 129250, probability: 75 },
        { level: 2750, profit: 179250, probability: 60 }
      ]
    },
    {
      id: 'eq_2',
      symbol: 'INFY',
      name: 'Infosys Ltd',
      strategy: 'Value Buy',
      confidence: 78,
      riskLevel: 'LOW',
      riskReward: '1:3',
      capitalRequired: 75000,
      expectedReturn: 8.5,
      holdingPeriod: '15-20 days',
      entryType: 'limit',
      entryPrice: 1580.00,
      targetPrice: 1680.00,
      stopLoss: 1500.00,
      maxProfit: 125000,
      maxLoss: 50000,
      currentPrice: 1650.00,
      exitPrice: 1650.00,
      reasoning: 'Undervalued with strong fundamentals, good dividend yield',
      technicalIndicators: ['RSI: 45', 'P/E: 18.5', 'Volume: Moderate'],
      marketCap: 'Large Cap',
      sector: 'IT Services',
      segment: 'equity',
      action: 'buy',
      status: 'closed',
      targets: [
        { level: 1680, profit: 5000, probability: 80 }
      ]
    },
  ],
  fno: [
    // Futures Strategies
    {
      id: 'ft_1',
      symbol: 'NIFTY50',
      name: 'Nifty 50 Future',
      strategy: 'Trend Following',
      confidence: 82,
      riskLevel: 'HIGH',
      capitalRequired: 100000,
      expectedReturn: 15.0,
      riskReward: '1:1.5',
      maxProfit: 325000,
      maxLoss: 225000,
      holdingPeriod: '3-5 days',
      entryType: 'market',
      targetPrice: 23500.00,
      stopLoss: 22400.00,
      reasoning: 'Strong uptrend with increasing volume, momentum indicators bullish',
      technicalIndicators: ['Moving Average: Bullish', 'Volume: Rising', 'Momentum: Strong'],
      expiry: '2024-01-25',
      segment: 'fno',
      strategyType: 'Futures',
      status: 'active',
      legs: [
        {
          id: 'ft_1_leg_1',
          action: 'buy',
          type: 'futures',
          symbol: 'NIFTY50-JAN',
          quantity: 1,
          entryPrice: 22850.00,
          currentPrice: 22950.00,
          lotSize: 50
        }
      ],
      targets: [
        { level: 23500, profit: 325000, probability: 70 },
        { level: 23800, profit: 475000, probability: 50 }
      ]
    },
    {
      id: 'ft_2',
      symbol: 'BANKNIFTY',
      name: 'Bank Nifty Future',
      strategy: 'Mean Reversion',
      confidence: 75,
      riskLevel: 'MID',
      capitalRequired: 80000,
      expectedReturn: 10.5,
      riskReward: '1:1.2',
      maxProfit: 175000,
      maxLoss: 150000,
      holdingPeriod: '2-3 days',
      entryType: 'limit',
      targetPrice: 49200.00,
      stopLoss: 47800.00,
      reasoning: 'Oversold condition, approaching support level',
      technicalIndicators: ['RSI: 35', 'Support: Strong', 'Volume: Low'],
      expiry: '2024-01-25',
      segment: 'fno',
      strategyType: 'Futures',
      status: 'closed',
      legs: [
        {
          id: 'ft_2_leg_1',
          action: 'sell',
          type: 'futures',
          symbol: 'BANKNIFTY-JAN',
          quantity: 1,
          entryPrice: 48500.00,
          currentPrice: 48650.00,
          exitPrice: 48650.00,
          lotSize: 25
        }
      ],
      targets: [
        { level: 49200, profit: 175000, probability: 65 }
      ]
    },
    // Options Strategies
    {
      id: 'opt_1',
      symbol: 'NIFTY',
      name: 'Nifty Bull Call Spread',
      strategy: 'Bull Call Spread',
      confidence: 88,
      riskLevel: 'MID',
      capitalRequired: 25000,
      expectedReturn: 25.0,
      riskReward: '1:3',
      maxProfit: 5000,
      maxLoss: 20000,
      holdingPeriod: '5-7 days',
      entryType: 'market',
      reasoning: 'Strong bullish momentum with high volatility',
      technicalIndicators: ['IV: High', 'Delta: 0.65', 'Theta: -2.5'],
      expiry: '2024-01-25',
      segment: 'fno',
      strategyType: 'Options',
      status: 'active',
      targets: [
        { level: 'Max Profit', profit: 5000, probability: 65 }
      ],
      legs: [
        { 
          id: 'opt_1_leg_1',
          action: 'buy', 
          type: 'options',
          symbol: 'NIFTY50-CALL-23000',
          quantity: 1,
          entryPrice: 180.50,
          currentPrice: 195.00,
          lotSize: 50
        },
        { 
          id: 'opt_1_leg_2',
          action: 'sell', 
          type: 'options',
          symbol: 'NIFTY50-CALL-23200',
          quantity: 1,
          entryPrice: 120.00,
          currentPrice: 135.00,
          lotSize: 50
        }
      ]
    },
    {
      id: 'opt_2',
      symbol: 'BANKNIFTY',
      name: 'Bank Nifty Protective Put',
      strategy: 'Protective Put',
      confidence: 72,
      riskLevel: 'VERY_LOW',
      capitalRequired: 15000,
      expectedReturn: 18.5,
      riskReward: '1:2',
      maxProfit: 3000,
      maxLoss: 15000,
      holdingPeriod: '3-5 days',
      entryType: 'limit',
      reasoning: 'Hedge against market volatility, defensive play',
      technicalIndicators: ['IV: Moderate', 'Delta: -0.45', 'Theta: -1.8'],
      expiry: '2024-01-25',
      segment: 'fno',
      strategyType: 'Options',
      status: 'active',
      targets: [
        { level: 140, profit: 3000, probability: 60 }
      ],
      legs: [
        { 
          id: 'opt_2_leg_1',
          action: 'buy', 
          type: 'options',
          symbol: 'BANKNIFTY-PUT-48500',
          quantity: 1,
          entryPrice: 95.00,
          currentPrice: 105.00,
          lotSize: 25
        }
      ]
    },
    {
      id: 'ft_3',
      symbol: 'NIFTY50',
      name: 'Nifty Calendar Spread',
      strategy: 'Calendar Spread',
      confidence: 88,
      riskLevel: 'LOW',
      capitalRequired: 50000,
      expectedReturn: 8.0,
      riskReward: '1:3',
      maxProfit: 50000,
      maxLoss: 25000,
      holdingPeriod: '10-15 days',
      entryType: 'limit',
      targetPrice: 23200.00,
      stopLoss: 22700.00,
      reasoning: 'Time decay strategy, selling near month, buying far month',
      technicalIndicators: ['Theta: High', 'Volatility: Moderate', 'Time Decay: Favorable'],
      expiry: '2024-01-25',
      segment: 'fno',
      strategyType: 'Futures',
      status: 'active',
      legs: [
        {
          id: 'ft_3_leg_1',
          action: 'buy',
          type: 'futures',
          symbol: 'NIFTY50-FEB',
          quantity: 1,
          entryPrice: 23100.00,
          currentPrice: 23150.00,
          lotSize: 50
        },
        {
          id: 'ft_3_leg_2',
          action: 'sell',
          type: 'futures',
          symbol: 'NIFTY50-JAN',
          quantity: 1,
          entryPrice: 22900.00,
          currentPrice: 22950.00,
          lotSize: 50
        }
      ],
      targets: [
        { level: 23200, profit: 50000, probability: 80 }
      ]
    },
    {
      id: 'hybrid_1',
      symbol: 'NIFTY50',
      name: 'Nifty Protective Put Strategy',
      strategy: 'Protective Put with Futures',
      confidence: 92,
      riskLevel: 'VERY_HIGH',
      capitalRequired: 75000,
      expectedReturn: 12.0,
      riskReward: '1:2.5',
      maxProfit: 87500,
      maxLoss: 25000,
      holdingPeriod: '7-10 days',
      entryType: 'limit',
      targetPrice: 23500.00,
      stopLoss: 22500.00,
      reasoning: 'Long futures with protective put hedge, limited downside risk',
      technicalIndicators: ['Trend: Bullish', 'Volatility: Moderate', 'Support: Strong'],
      expiry: '2024-01-25',
      segment: 'fno',
      strategyType: 'Hybrid',
      status: 'active',
      legs: [
        {
          id: 'hybrid_1_leg_1',
          action: 'buy',
          type: 'futures',
          symbol: 'NIFTY50-FEB',
          quantity: 1,
          entryPrice: 23100.00,
          currentPrice: 23150.00,
          lotSize: 50
        },
        {
          id: 'hybrid_1_leg_2',
          action: 'buy',
          type: 'options',
          symbol: 'NIFTY50-PUT-23000',
          quantity: 1,
          entryPrice: 120.00,
          currentPrice: 95.00,
          lotSize: 50
        }
      ],
      targets: [
        { level: 23500, profit: 87500, probability: 75 }
      ]
    },
    {
      id: 'hybrid_2',
      symbol: 'BANKNIFTY',
      name: 'Bank Nifty Covered Call',
      strategy: 'Covered Call Strategy',
      confidence: 85,
      riskLevel: 'LOW',
      capitalRequired: 100000,
      expectedReturn: 8.5,
      riskReward: '1:1.8',
      maxProfit: 45000,
      maxLoss: 15000,
      holdingPeriod: '15-20 days',
      entryType: 'market',
      targetPrice: 49000.00,
      stopLoss: 48000.00,
      reasoning: 'Long futures with covered call for income generation',
      technicalIndicators: ['Trend: Sideways', 'Volatility: Low', 'Theta: Favorable'],
      expiry: '2024-01-25',
      segment: 'fno',
      strategyType: 'Hybrid',
      status: 'closed',
      legs: [
        {
          id: 'hybrid_2_leg_1',
          action: 'buy',
          type: 'futures',
          symbol: 'BANKNIFTY-JAN',
          quantity: 2,
          entryPrice: 48500.00,
          currentPrice: 48650.00,
          exitPrice: 48650.00,
          lotSize: 25
        },
        {
          id: 'hybrid_2_leg_2',
          action: 'sell',
          type: 'options',
          symbol: 'BANKNIFTY-CALL-49000',
          quantity: 2,
          entryPrice: 180.00,
          currentPrice: 120.00,
          exitPrice: 120.00,
          lotSize: 25
        }
      ],
      targets: [
        { level: 49000, profit: 45000, probability: 70 }
      ]
    },
  ],
};

export const mockMarketData = {
  indices: [
    { symbol: 'NIFTY50', price: 22850.25, change: 125.50, changePercent: 0.55 },
    { symbol: 'BANKNIFTY', price: 48520.75, change: -85.25, changePercent: -0.18 },
    { symbol: 'SENSEX', price: 75250.30, change: 245.80, changePercent: 0.33 },
  ],
  vix: 18.5,
  marketStatus: 'open',
};
