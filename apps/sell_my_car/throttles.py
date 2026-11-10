from rest_framework.throttling import SimpleRateThrottle


class IPRateThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class SellMyCarLookupThrottle(IPRateThrottle):
    scope = "sell_my_car_lookup"
    rate = "30/hour"


class SellMyCarSubmitThrottle(IPRateThrottle):
    scope = "sell_my_car_submit"
    rate = "10/hour"
