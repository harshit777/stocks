"""
Trading Cost Calculator

Calculates accurate trading costs including:
- Brokerage
- STT (Securities Transaction Tax)
- Exchange charges
- GST
- Stamp duty
- SEBI charges
"""
from typing import Dict


class CostCalculator:
    """
    Calculate real trading costs for NSE equity intraday and delivery.
    
    Based on Zerodha pricing as of 2024.
    """
    
    def __init__(self, broker: str = "zerodha"):
        """
        Initialize cost calculator.
        
        Args:
            broker: Broker name (currently supports "zerodha")
        """
        self.broker = broker
        
        # Zerodha brokerage rates
        self.brokerage_flat = 20.0  # ₹20 per executed order
        self.brokerage_pct = 0.0003  # 0.03% or ₹20, whichever is lower
        
        # Statutory charges
        self.stt_intraday = 0.00025  # 0.025% on sell side only
        self.stt_delivery = 0.001  # 0.1% on both buy and sell
        self.exchange_charge = 0.0000325  # 0.00325%
        self.sebi_charge = 0.000001  # ₹10 per crore
        self.gst_rate = 0.18  # 18% on brokerage + transaction charges
        self.stamp_duty = 0.00015  # 0.015% or ₹1500 per crore on buy side
    
    def calculate_brokerage(self, trade_value: float, product: str = "MIS") -> float:
        """
        Calculate brokerage for a trade.
        
        Args:
            trade_value: Total trade value (price * quantity)
            product: MIS (intraday) or CNC (delivery)
        
        Returns:
            Brokerage amount
        """
        if product == "MIS":
            # Intraday: ₹20 or 0.03% whichever is lower
            percentage_based = trade_value * self.brokerage_pct
            return min(self.brokerage_flat, percentage_based)
        else:
            # Delivery: ₹0 at Zerodha for equity delivery
            return 0.0
    
    def calculate_stt(self, trade_value: float, transaction_type: str, product: str = "MIS") -> float:
        """
        Calculate STT (Securities Transaction Tax).
        
        Args:
            trade_value: Total trade value
            transaction_type: BUY or SELL
            product: MIS or CNC
        
        Returns:
            STT amount
        """
        if product == "MIS":
            # Intraday: 0.025% on sell side only
            if transaction_type == "SELL":
                return trade_value * self.stt_intraday
            return 0.0
        else:
            # Delivery: 0.1% on both buy and sell
            return trade_value * self.stt_delivery
    
    def calculate_exchange_charges(self, trade_value: float) -> float:
        """
        Calculate exchange transaction charges.
        
        Args:
            trade_value: Total trade value
        
        Returns:
            Exchange charges
        """
        return trade_value * self.exchange_charge
    
    def calculate_sebi_charges(self, trade_value: float) -> float:
        """
        Calculate SEBI turnover charges.
        
        Args:
            trade_value: Total trade value
        
        Returns:
            SEBI charges
        """
        return trade_value * self.sebi_charge
    
    def calculate_stamp_duty(self, trade_value: float, transaction_type: str) -> float:
        """
        Calculate stamp duty.
        
        Args:
            trade_value: Total trade value
            transaction_type: BUY or SELL
        
        Returns:
            Stamp duty amount
        """
        if transaction_type == "BUY":
            # 0.015% on buy side only, capped at ₹1500 per crore
            stamp = trade_value * self.stamp_duty
            max_stamp = (trade_value / 10000000) * 1500  # ₹1500 per crore
            return min(stamp, max_stamp)
        return 0.0
    
    def calculate_gst(self, taxable_amount: float) -> float:
        """
        Calculate GST on brokerage and transaction charges.
        
        Args:
            taxable_amount: Sum of brokerage + exchange charges + SEBI charges
        
        Returns:
            GST amount
        """
        return taxable_amount * self.gst_rate
    
    def calculate_total_cost(
        self, 
        price: float, 
        quantity: int, 
        transaction_type: str,
        product: str = "MIS"
    ) -> Dict[str, float]:
        """
        Calculate total trading cost with breakdown.
        
        Args:
            price: Trade price per share
            quantity: Number of shares
            transaction_type: BUY or SELL
            product: MIS (intraday) or CNC (delivery)
        
        Returns:
            Dictionary with cost breakdown
        """
        trade_value = price * quantity
        
        # Calculate individual components
        brokerage = self.calculate_brokerage(trade_value, product)
        stt = self.calculate_stt(trade_value, transaction_type, product)
        exchange_charges = self.calculate_exchange_charges(trade_value)
        sebi_charges = self.calculate_sebi_charges(trade_value)
        stamp_duty = self.calculate_stamp_duty(trade_value, transaction_type)
        
        # GST is on brokerage + exchange charges + SEBI charges
        taxable_amount = brokerage + exchange_charges + sebi_charges
        gst = self.calculate_gst(taxable_amount)
        
        # Total cost
        total_cost = brokerage + stt + exchange_charges + sebi_charges + gst + stamp_duty
        
        return {
            'trade_value': trade_value,
            'brokerage': round(brokerage, 2),
            'stt': round(stt, 2),
            'exchange_charges': round(exchange_charges, 2),
            'sebi_charges': round(sebi_charges, 2),
            'gst': round(gst, 2),
            'stamp_duty': round(stamp_duty, 2),
            'total_cost': round(total_cost, 2),
            'cost_percentage': round((total_cost / trade_value * 100), 4) if trade_value > 0 else 0
        }
    
    def calculate_round_trip_cost(
        self,
        buy_price: float,
        sell_price: float,
        quantity: int,
        product: str = "MIS"
    ) -> Dict[str, float]:
        """
        Calculate total cost for a round trip (buy + sell).
        
        Args:
            buy_price: Buy price per share
            sell_price: Sell price per share
            quantity: Number of shares
            product: MIS or CNC
        
        Returns:
            Dictionary with round trip cost breakdown
        """
        buy_costs = self.calculate_total_cost(buy_price, quantity, "BUY", product)
        sell_costs = self.calculate_total_cost(sell_price, quantity, "SELL", product)
        
        total_cost = buy_costs['total_cost'] + sell_costs['total_cost']
        gross_profit = (sell_price - buy_price) * quantity
        net_profit = gross_profit - total_cost
        
        return {
            'buy_value': buy_costs['trade_value'],
            'sell_value': sell_costs['trade_value'],
            'buy_costs': buy_costs['total_cost'],
            'sell_costs': sell_costs['total_cost'],
            'total_costs': round(total_cost, 2),
            'gross_profit': round(gross_profit, 2),
            'net_profit': round(net_profit, 2),
            'return_percentage': round((net_profit / buy_costs['trade_value'] * 100), 2) if buy_costs['trade_value'] > 0 else 0,
            'cost_breakdown': {
                'buy': buy_costs,
                'sell': sell_costs
            }
        }
    
    def get_breakeven_price(
        self,
        buy_price: float,
        quantity: int,
        product: str = "MIS"
    ) -> float:
        """
        Calculate breakeven sell price (including all costs).
        
        Args:
            buy_price: Purchase price
            quantity: Number of shares
            product: MIS or CNC
        
        Returns:
            Breakeven sell price
        """
        # Calculate buy costs
        buy_costs = self.calculate_total_cost(buy_price, quantity, "BUY", product)
        
        # Estimate sell costs (iterative approach for accuracy)
        # Start with buy price as estimate
        sell_price_estimate = buy_price
        
        for _ in range(5):  # Iterate to converge
            sell_costs = self.calculate_total_cost(sell_price_estimate, quantity, "SELL", product)
            total_costs = buy_costs['total_cost'] + sell_costs['total_cost']
            
            # Breakeven: sell_value = buy_value + total_costs
            required_sell_value = buy_costs['trade_value'] + total_costs
            sell_price_estimate = required_sell_value / quantity
        
        return round(sell_price_estimate, 2)


# Global instance
_cost_calculator = None


def get_cost_calculator() -> CostCalculator:
    """Get global cost calculator instance."""
    global _cost_calculator
    if _cost_calculator is None:
        _cost_calculator = CostCalculator()
    return _cost_calculator
