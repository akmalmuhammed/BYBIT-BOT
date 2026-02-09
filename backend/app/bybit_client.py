"""
Bybit API Client
Wrapper for Bybit Futures API - Live Trading
"""
import hmac
import hashlib
import time
import requests
from typing import Optional, Dict, Any
from .config import BYBIT_API_KEY, BYBIT_API_SECRET


class BybitClient:
    """Bybit Futures API client for live trading."""
    
    BASE_URL = "https://api.bybit.com"
    
    def __init__(self, api_key: str = None, api_secret: str = None, testnet: bool = False):
        self.api_key = api_key or BYBIT_API_KEY
        self.api_secret = api_secret or BYBIT_API_SECRET
        
        if testnet:
            self.BASE_URL = "https://api-testnet.bybit.com"
        
        if not self.api_key or not self.api_secret:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET must be set")
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC SHA256 signature for request."""
        timestamp = str(int(time.time() * 1000))
        param_str = timestamp + self.api_key + "5000"  # recv_window
        
        if params:
            sorted_params = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
            param_str += sorted_params
        
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature, timestamp
    
    def _request(self, method: str, endpoint: str, params: Dict = None) -> Dict:
        """Make authenticated request to Bybit API."""
        params = params or {}
        
        signature, timestamp = self._generate_signature(params)
        
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json"
        }
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=10)
            else:
                response = requests.post(url, headers=headers, json=params, timeout=10)
            
            data = response.json()
            
            if data.get("retCode") != 0:
                print(f"⚠️ Bybit API Error: {data.get('retMsg', 'Unknown error')}")
            
            return data
            
        except Exception as e:
            print(f"❌ Bybit API Request failed: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    # === Account Methods ===
    
    def get_wallet_balance(self, coin: str = "USDT") -> Optional[float]:
        """Get wallet balance for a coin."""
        result = self._request("GET", "/v5/account/wallet-balance", {
            "accountType": "UNIFIED",
            "coin": coin
        })
        
        if result.get("retCode") == 0:
            try:
                coins = result["result"]["list"][0]["coin"]
                for c in coins:
                    if c["coin"] == coin:
                        return float(c["walletBalance"])
            except (KeyError, IndexError):
                pass
        return None
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol."""
        result = self._request("POST", "/v5/position/set-leverage", {
            "category": "linear",
            "symbol": symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        })
        
        # retCode 110043 means leverage already set to this value
        return result.get("retCode") in [0, 110043]
    
    # === Order Methods ===
    
    def place_market_order(self, symbol: str, side: str, qty: float, 
                           reduce_only: bool = False) -> Optional[str]:
        """
        Place a market order.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: "Buy" or "Sell"
            qty: Quantity in base currency
            reduce_only: If True, only reduce position
            
        Returns:
            Order ID if successful, None otherwise
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "GTC"
        }
        
        if reduce_only:
            params["reduceOnly"] = True
        
        result = self._request("POST", "/v5/order/create", params)
        
        if result.get("retCode") == 0:
            order_id = result["result"].get("orderId")
            print(f"✅ Market order placed: {side} {qty} {symbol} | Order ID: {order_id}")
            return order_id
        
        return None
    
    def set_trading_stop(self, symbol: str, side: str, 
                         stop_loss: float = None, take_profit: float = None) -> bool:
        """
        Set stop loss and/or take profit for an open position.
        
        Args:
            symbol: Trading pair
            side: Position side - "Buy" for long, "Sell" for short
            stop_loss: Stop loss price
            take_profit: Take profit price
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "positionIdx": 0  # One-way mode
        }
        
        if stop_loss:
            params["stopLoss"] = str(stop_loss)
            params["slTriggerBy"] = "LastPrice"
        
        if take_profit:
            params["takeProfit"] = str(take_profit)
            params["tpTriggerBy"] = "LastPrice"
        
        result = self._request("POST", "/v5/position/trading-stop", params)
        
        if result.get("retCode") == 0:
            print(f"✅ Trading stop set for {symbol}: SL={stop_loss}, TP={take_profit}")
            return True
        
        return False
    
    # === Position Methods ===
    
    def get_positions(self, symbol: str = None) -> list:
        """Get open positions."""
        params = {
            "category": "linear",
            "settleCoin": "USDT"
        }
        
        if symbol:
            params["symbol"] = symbol
        
        result = self._request("GET", "/v5/position/list", params)
        
        if result.get("retCode") == 0:
            positions = result["result"].get("list", [])
            # Filter for actual open positions (size > 0)
            return [p for p in positions if float(p.get("size", 0)) > 0]
        
        return []
    
    def close_position(self, symbol: str, side: str) -> bool:
        """
        Close an open position at market price.
        
        Args:
            symbol: Trading pair
            side: Current position side ("LONG" or "SHORT")
        """
        # To close, we place opposite order with reduce_only
        close_side = "Sell" if side == "LONG" else "Buy"
        
        # Get position size
        positions = self.get_positions(symbol)
        for pos in positions:
            if pos["symbol"] == symbol:
                qty = float(pos["size"])
                if qty > 0:
                    order_id = self.place_market_order(symbol, close_side, qty, reduce_only=True)
                    if order_id:
                        print(f"🔴 Position closed: {symbol}")
                        return True
        
        return False
    
    # === Utility Methods ===
    
    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """Get current ticker price."""
        result = self._request("GET", "/v5/market/tickers", {
            "category": "linear",
            "symbol": symbol
        })
        
        if result.get("retCode") == 0:
            try:
                return float(result["result"]["list"][0]["lastPrice"])
            except (KeyError, IndexError):
                pass
        return None
    
    def get_instrument_info(self, symbol: str) -> Optional[Dict]:
        """Get instrument info for calculating lot sizes."""
        result = self._request("GET", "/v5/market/instruments-info", {
            "category": "linear",
            "symbol": symbol
        })
        
        if result.get("retCode") == 0:
            try:
                return result["result"]["list"][0]
            except (KeyError, IndexError):
                pass
        return None
    
    def calculate_qty(self, symbol: str, usd_amount: float, leverage: int = 8) -> Optional[float]:
        """
        Calculate quantity to trade based on USD amount and leverage.
        
        Args:
            symbol: Trading pair
            usd_amount: Amount in USD to trade
            leverage: Leverage multiplier
            
        Returns:
            Quantity in base currency
        """
        price = self.get_ticker_price(symbol)
        if not price:
            return None
        
        info = self.get_instrument_info(symbol)
        if not info:
            return None
        
        # Calculate raw qty
        position_value = usd_amount * leverage
        qty = position_value / price
        
        # Round to lot size
        lot_size = float(info.get("lotSizeFilter", {}).get("qtyStep", "0.001"))
        qty = round(qty / lot_size) * lot_size
        
        # Check min qty
        min_qty = float(info.get("lotSizeFilter", {}).get("minOrderQty", "0"))
        if qty < min_qty:
            qty = min_qty
        
        return round(qty, 6)


# Singleton instance
_client: Optional[BybitClient] = None


def get_client(testnet: bool = False) -> BybitClient:
    """Get or create Bybit client instance."""
    global _client
    if _client is None:
        _client = BybitClient(testnet=testnet)
    return _client
