def calculate_cost(distance_meters: float) -> float:
    if distance_meters == 0:
        return 0.0
    
    BASE_FIBER_RATE_PER_METER = 700
    cost = distance_meters * BASE_FIBER_RATE_PER_METER
    return round(cost, 2)
