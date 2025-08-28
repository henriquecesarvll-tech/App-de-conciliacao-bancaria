import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from cache_service import cache
    print("Testando cache...")
    
    # Teste básico
    cache.set('teste', {'msg': 'ok'}, 'test')
    result = cache.get('teste', 'test')
    print(f"Resultado: {result}")
    
    # Stats
    stats = cache.get_stats()
    print(f"Stats: {stats}")
    
    # Health
    health = cache.health_check()
    print(f"Health: {health}")
    
    print("Cache funcionando!")
    
except Exception as e:
    print(f"Erro: {e}")
    import traceback
    traceback.print_exc()