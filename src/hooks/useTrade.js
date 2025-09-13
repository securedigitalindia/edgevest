import { useState, useEffect, useCallback } from 'react';
import tradeService from '../services/tradeService';

export const useTrade = () => {
  const [segments, setSegments] = useState([]);
  const [allStrategies, setAllStrategies] = useState([]);
  const [strategies, setStrategies] = useState([]);
  const [marketData, setMarketData] = useState(null);
  const [selectedSegment, setSelectedSegment] = useState(null);
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [tradeStatus, setTradeStatus] = useState('active');
  const [livePrices, setLivePrices] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch trading segments
  const fetchSegments = useCallback(async () => {
    try {
      setLoading(true);
      const data = await tradeService.getTradingSegments();
      setSegments(data);
      setError(null);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching segments:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch strategies for selected segment
  const fetchStrategies = useCallback(async (segment) => {
    try {
      setLoading(true);
      const data = await tradeService.getStrategiesBySegment(segment);
      setAllStrategies(data);
      // Filter by status
      const filteredData = data.filter(strategy => strategy.status === tradeStatus);
      setStrategies(filteredData);
      setError(null);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching strategies:', err);
    } finally {
      setLoading(false);
    }
  }, [tradeStatus]);

  // Filter strategies by status
  const filterStrategiesByStatus = useCallback((status) => {
    setTradeStatus(status);
    const filteredData = allStrategies.filter(strategy => strategy.status === status);
    setStrategies(filteredData);
  }, [allStrategies]);

  // Fetch market data
  const fetchMarketData = useCallback(async () => {
    try {
      const data = await tradeService.getMarketData();
      setMarketData(data);
    } catch (err) {
      console.error('Error fetching market data:', err);
    }
  }, []);

  // Fetch live price for a symbol
  const fetchLivePrice = useCallback(async (symbol) => {
    try {
      const priceData = await tradeService.getLivePrice(symbol);
      setLivePrices(prev => ({
        ...prev,
        [symbol]: priceData
      }));
    } catch (err) {
      console.error('Error fetching live price:', err);
    }
  }, []);

  // Execute trade
  const executeTrade = async (tradeData) => {
    try {
      setLoading(true);
      const result = await tradeService.executeTrade(tradeData);
      setError(null);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  // Get risk analysis
  const getRiskAnalysis = async (strategyId) => {
    try {
      const analysis = await tradeService.getRiskAnalysis(strategyId);
      return analysis;
    } catch (err) {
      console.error('Error fetching risk analysis:', err);
      throw err;
    }
  };

  // Handle segment change
  const handleSegmentChange = useCallback((segment) => {
    const segmentId = typeof segment === 'object' ? segment.id : segment;
    setSelectedSegment(segmentId);
    setSelectedStrategy(null);
    fetchStrategies(segmentId);
  }, [fetchStrategies]);

  // Handle strategy selection
  const handleStrategySelect = useCallback((strategy) => {
    setSelectedStrategy(strategy);
    // Fetch live price for the strategy symbol
    if (strategy.symbol) {
      fetchLivePrice(strategy.symbol);
    }
  }, [fetchLivePrice]);

  // Refresh data
  const refreshData = useCallback(() => {
    fetchSegments();
    fetchStrategies(selectedSegment);
    fetchMarketData();
  }, [fetchSegments, fetchStrategies, fetchMarketData, selectedSegment]);

  // Initialize data
  useEffect(() => {
    fetchSegments();
    fetchMarketData();
  }, [fetchSegments, fetchMarketData]);

  // Load strategies when segment changes
  useEffect(() => {
    if (selectedSegment) {
      fetchStrategies(selectedSegment);
    }
  }, [selectedSegment, fetchStrategies]);

  // Set up live price updates
  useEffect(() => {
    const interval = setInterval(() => {
      strategies.forEach(strategy => {
        if (strategy.symbol) {
          fetchLivePrice(strategy.symbol);
        }
      });
    }, 5000); // Update every 5 seconds

    return () => clearInterval(interval);
  }, [strategies, fetchLivePrice]);

  return {
    // Data
    segments,
    strategies,
    marketData,
    selectedSegment,
    selectedStrategy,
    livePrices,
    loading,
    error,
    
    // Actions
    handleSegmentChange,
    handleStrategySelect,
    executeTrade,
    getRiskAnalysis,
    refreshData,
    filterStrategiesByStatus,
    
    // Utilities
    setSelectedSegment,
    setSelectedStrategy,
    tradeStatus,
  };
};
