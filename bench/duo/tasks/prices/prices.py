def total(prices, discount_percent=0):
    """Return the order total in rupees, rounded to 2 decimal places.

    - prices: a list of item prices (numbers, each >= 0). An empty list totals 0.0.
    - discount_percent: a percentage from 0 to 100 inclusive, applied to the whole subtotal.
    - Raise ValueError if any price is negative or if discount_percent is outside 0..100.
    - Rounding is half-up to the paisa: 10.005 becomes 10.01 (not banker's rounding, not float drift).
    """
    subtotal = sum(prices)
    return round(subtotal - discount_percent, 2)
