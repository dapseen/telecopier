"""Test script for MT5 order sending with take profits.

This script tests different approaches to sending orders with take profits:
1. Direct order with TPs
2. Two-step approach (order first, then modify)
"""

import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, Any

import MetaTrader5 as mt5
import structlog
from dotenv import load_dotenv

logger = structlog.get_logger(__name__)

class MT5TestOrder:
    def __init__(self):
        self.mt5 = mt5
        self._connected = False
        
    async def connect(self) -> bool:
        """Connect to MT5."""
        if not self.mt5.initialize():
            logger.error("mt5_initialize_failed", error=self.mt5.last_error())
            return False
            
        # Load credentials from env
        load_dotenv()
        login = int(os.getenv("MT5_LOGIN"))
        password = os.getenv("MT5_PASSWORD")
        server = os.getenv("MT5_SERVER")
        
        if not self.mt5.login(login=login, password=password, server=server):
            logger.error("mt5_login_failed", error=self.mt5.last_error())
            return False
            
        self._connected = True
        logger.info("mt5_connected", server=server, login=login)
        return True
        
    async def disconnect(self):
        """Disconnect from MT5."""
        if self._connected:
            self.mt5.shutdown()
            self._connected = False
            logger.info("mt5_disconnected")
            
    async def test_direct_order(self, symbol: str, volume: float, sl: float, tps: list[float]) -> Dict[str, Any]:
        """Test sending order with TPs directly."""
        try:
            # Get symbol info
            symbol_info = self.mt5.symbol_info(symbol)
            if not symbol_info:
                return {"success": False, "error": f"Symbol {symbol} not found"}
                
            # Get current price
            tick = self.mt5.symbol_info_tick(symbol)
            if not tick:
                return {"success": False, "error": "Failed to get current price"}
                
            # Log market conditions
            logger.info(
                "market_conditions",
                symbol=symbol,
                bid=tick.bid,
                ask=tick.ask,
                spread=tick.ask - tick.bid,
                volume=volume,
                sl=sl,
                tps=tps
            )
            
            # Try to send order with first TP
            request = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": self.mt5.ORDER_TYPE_BUY,
                "price": tick.ask,
                "sl": sl,
                "tp": tps[0],  # First TP
                "deviation": 10,
                "magic": 12345,
                "comment": f"Test Direct Order TP1",
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }
            
            # Log order request
            logger.info("sending_direct_order", request=request)
            
            # Send order
            result = self.mt5.order_send(request)
            if not result:
                return {"success": False, "error": "order_send returned None"}
                
            # Log result
            logger.info(
                "direct_order_result",
                retcode=result.retcode,
                comment=result.comment,
                order=result.order if hasattr(result, 'order') else None,
                volume=result.volume if hasattr(result, 'volume') else None,
                price=result.price if hasattr(result, 'price') else None
            )
            
            if result.retcode != self.mt5.TRADE_RETCODE_DONE:
                return {
                    "success": False,
                    "error": f"Order failed: {result.comment} (code: {result.retcode})"
                }
                
            return {
                "success": True,
                "order": result.order,
                "price": result.price,
                "volume": result.volume
            }
            
        except Exception as e:
            logger.error("direct_order_error", error=str(e))
            return {"success": False, "error": str(e)}
            
    async def test_two_step_order(self, symbol: str, volume: float, sl: float, tps: list[float]) -> Dict[str, Any]:
        """Test two-step order approach (place order first, then modify with TP)."""
        try:
            # Get symbol info and current price
            symbol_info = self.mt5.symbol_info(symbol)
            tick = self.mt5.symbol_info_tick(symbol)
            if not symbol_info or not tick:
                return {"success": False, "error": "Failed to get market data"}
                
            # Log market conditions
            logger.info(
                "market_conditions",
                symbol=symbol,
                bid=tick.bid,
                ask=tick.ask,
                spread=tick.ask - tick.bid,
                volume=volume,
                sl=sl,
                tps=tps
            )
            
            # Step 1: Place order without SL/TP
            request = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": self.mt5.ORDER_TYPE_BUY,
                "price": tick.ask,
                "deviation": 10,
                "magic": 12345,
                "comment": "Test Two-Step Order",
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }
            
            # Log initial request
            logger.info("sending_initial_order", request=request)
            
            # Send initial order
            result = self.mt5.order_send(request)
            if not result:
                return {"success": False, "error": "Initial order_send returned None"}
                
            # Log initial result
            logger.info(
                "initial_order_result",
                retcode=result.retcode,
                comment=result.comment,
                order=result.order if hasattr(result, 'order') else None
            )
            
            if result.retcode != self.mt5.TRADE_RETCODE_DONE:
                return {
                    "success": False,
                    "error": f"Initial order failed: {result.comment} (code: {result.retcode})"
                }
                
            # Step 2: Modify with SL/TP
            # Wait a bit for order to be processed
            await asyncio.sleep(1)
            
            # Get position
            position = self.mt5.positions_get(ticket=result.order)
            if not position:
                return {"success": False, "error": "Position not found after order"}
                
            position = position[0]
            
            # Try to modify with first TP
            modify_request = {
                "action": self.mt5.TRADE_ACTION_SLTP,
                "symbol": symbol,
                "position": position.ticket,
                "sl": sl,
                "tp": tps[0]  # First TP
            }
            
            # Log modification request
            logger.info("sending_modify_request", request=modify_request)
            
            # Send modification
            modify_result = self.mt5.order_send(modify_request)
            if not modify_result:
                return {"success": False, "error": "Modification order_send returned None"}
                
            # Log modification result
            logger.info(
                "modification_result",
                retcode=modify_result.retcode,
                comment=modify_result.comment
            )
            
            if modify_result.retcode != self.mt5.TRADE_RETCODE_DONE:
                return {
                    "success": False,
                    "error": f"Modification failed: {modify_result.comment} (code: {modify_result.retcode})"
                }
                
            return {
                "success": True,
                "order": result.order,
                "price": result.price,
                "volume": result.volume,
                "modified": True
            }
            
        except Exception as e:
            logger.error("two_step_order_error", error=str(e))
            return {"success": False, "error": str(e)}

async def main():
    """Main test function."""
    # Test parameters
    symbol = "XAUUSD"
    volume = 0.28  # Lot size
    sl = 3301.0  # Stop loss
    tps = [3348.0, 3352.0, 3360.0, 3377.0]  # Take profits
    
    tester = MT5TestOrder()
    
    try:
        # Connect
        if not await tester.connect():
            logger.error("connection_failed")
            return
            
        # Test direct order
        logger.info("testing_direct_order")
        direct_result = await tester.test_direct_order(symbol, volume, sl, tps)
        logger.info("direct_order_complete", result=direct_result)
        
        # Wait between tests
        await asyncio.sleep(2)
        
        # Test two-step order
        logger.info("testing_two_step_order")
        two_step_result = await tester.test_two_step_order(symbol, volume, sl, tps)
        logger.info("two_step_order_complete", result=two_step_result)
        
    finally:
        # Disconnect
        await tester.disconnect()

if __name__ == "__main__":
    asyncio.run(main()) 